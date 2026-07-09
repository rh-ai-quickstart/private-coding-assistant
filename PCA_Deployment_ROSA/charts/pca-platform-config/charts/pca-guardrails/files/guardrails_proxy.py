"""
Guardrails Proxy — transparent OpenAI-compatible endpoint.

Accepts standard /v1/chat/completions requests from IDE extensions,
injects the configured detectors, forwards to the TrustyAI orchestrator
detection API, and returns the response. When the client requests streaming,
the proxy fetches the full response non-streaming (to avoid orchestrator
streaming issues with thinking mode) and converts it to SSE chunks.

Config via environment variables:
  ORCHESTRATOR_URL  — orchestrator base URL (default: https://pca-guardrails-service:8032)
  DETECTORS_JSON    — JSON detectors to inject into every request
  LISTEN_PORT       — port to listen on (default: 8080)
"""

import json
import os
import ssl
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "https://pca-guardrails-service:8032")
DETECTORS = json.loads(os.environ.get("DETECTORS_JSON", "{}"))
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "8080"))

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


def completion_to_sse_chunks(body):
    """Convert a non-streaming chat completion response to SSE chunks."""
    chunks = []
    for choice in body.get("choices", []):
        msg = choice.get("message", {})
        chunk = {
            "id": body.get("id", ""),
            "object": "chat.completion.chunk",
            "created": body.get("created", int(time.time())),
            "model": body.get("model", ""),
            "choices": [
                {
                    "index": choice.get("index", 0),
                    "delta": {
                        "role": msg.get("role", "assistant"),
                        "content": msg.get("content", ""),
                    },
                    "finish_reason": choice.get("finish_reason"),
                }
            ],
        }
        chunks.append(f"data: {json.dumps(chunk)}\n\n")

    if body.get("detections") or body.get("warnings"):
        reasons = []
        for direction in ("input", "output"):
            for msg_det in (body.get("detections") or {}).get(direction) or []:
                for r in msg_det.get("results", []):
                    det_id = r.get("detector_id", "unknown")
                    det_type = r.get("detection_type", "")
                    text = r.get("text", "")
                    score = r.get("score", 0)
                    if det_id == "prompt_injection":
                        reasons.append(f"Prompt injection detected (confidence: {score:.1%})")
                    elif det_type == "pii":
                        reasons.append(f'PII detected: {r.get("detection", det_id)} — "{text}"')
                    else:
                        reasons.append(
                            f'Credential/secret detected: {r.get("detection", det_id)} — "{text}"'
                        )

        if reasons and not body.get("choices"):
            message = "**Guardrails blocked your message.**\n\n" + "\n".join(
                f"- {r}" for r in reasons
            )
            blocked_chunk = {
                "id": body.get("id", ""),
                "object": "chat.completion.chunk",
                "created": body.get("created", int(time.time())),
                "model": body.get("model", ""),
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": message},
                        "finish_reason": "stop",
                    }
                ],
            }
            chunks.append(f"data: {json.dumps(blocked_chunk)}\n\n")

    chunks.append("data: [DONE]\n\n")
    return "".join(chunks)


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        client_wants_stream = body.get("stream", False)

        body["detectors"] = DETECTORS
        body["stream"] = False
        body.pop("stream_options", None)
        body.setdefault("chat_template_kwargs", {})["enable_thinking"] = False

        target = f"{ORCHESTRATOR_URL}/api/v2/chat/completions-detection"
        req = Request(
            target,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            resp = urlopen(req, context=SSL_CTX)
            resp_body = resp.read()

            if client_wants_stream:
                resp_json = json.loads(resp_body)
                sse = completion_to_sse_chunks(resp_json)
                sse_bytes = sse.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Content-Length", str(len(sse_bytes)))
                self.end_headers()
                self.wfile.write(sse_bytes)
            else:
                self.send_response(resp.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp_body)))
                self.end_headers()
                self.wfile.write(resp_body)
        except HTTPError as e:
            err_body = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err_body)))
            self.end_headers()
            self.wfile.write(err_body)
        except URLError as e:
            err = json.dumps({"error": str(e.reason)}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)

    def do_GET(self):
        if self.path == "/healthz":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")
            return
        target = f"{ORCHESTRATOR_URL}{self.path}"
        req = Request(target, method="GET")
        try:
            resp = urlopen(req, context=SSL_CTX)
            data = resp.read()
            self.send_response(resp.status)
            self.send_header("Content-Type", resp.headers.get("content-type", "application/json"))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (HTTPError, URLError):
            self.send_response(502)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def log_message(self, fmt, *args):
        print(f"[proxy] {fmt % args}", flush=True)


if __name__ == "__main__":
    print(f"[proxy] starting on :{LISTEN_PORT}", flush=True)
    print(f"[proxy] orchestrator: {ORCHESTRATOR_URL}", flush=True)
    print(f"[proxy] detectors: {json.dumps(DETECTORS, indent=2)}", flush=True)
    server = HTTPServer(("0.0.0.0", LISTEN_PORT), ProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
