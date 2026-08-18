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
  LANGFUSE_BASE_URL / LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY
                    — optional; empty keys skip flagged-trace ingest
"""

from __future__ import annotations

import base64
import json
import os
import ssl
import time
import uuid
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "https://pca-guardrails-service:8032")
DETECTORS = json.loads(os.environ.get("DETECTORS_JSON", "{}"))
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "8080"))
LANGFUSE_BASE_URL = os.environ.get(
    "LANGFUSE_BASE_URL",
    "http://pca-langfuse-web:3000",
).rstrip("/")

# Identity headers forwarded to the orchestrator / LLM for Langfuse attribution.
PCA_FORWARD_HEADERS = ("X-PCA-User", "X-PCA-Team", "X-PCA-DevSpace")

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

_EMIT_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pca-guardrails-lf")
_blocked_total = 0

DetectorHit = namedtuple(
    "DetectorHit",
    "detector_id detection_type detection text score direction",
)
# action: "" allowed, "block" empty choices, "warn" flagged with choices kept
GuardrailsOutcome = namedtuple("GuardrailsOutcome", "action hits")


def _forward_pca_headers(incoming):
    """Copy X-PCA-* attribution headers from the client request."""
    out = {"Content-Type": "application/json"}
    for name in PCA_FORWARD_HEADERS:
        value = incoming.get(name)
        if value:
            out[name] = value
    return out


def _header(incoming, name):
    if incoming is None:
        return None
    getter = getattr(incoming, "get", None)
    if not callable(getter):
        return None
    value = getter(name) or getter(name.lower())
    if value:
        return str(value)
    return None


def parse_guardrails_outcome(body):
    """Parse TrustyAI chat-completions-detection JSON into a domain outcome."""
    if not isinstance(body, dict):
        return GuardrailsOutcome("", ())
    hits = []
    detections = body.get("detections") or {}
    if not isinstance(detections, dict):
        detections = {}
    for direction in ("input", "output"):
        for msg_det in detections.get(direction) or []:
            if not isinstance(msg_det, dict):
                continue
            for raw in msg_det.get("results") or []:
                if not isinstance(raw, dict):
                    continue
                hits.append(
                    DetectorHit(
                        detector_id=str(raw.get("detector_id") or "unknown"),
                        detection_type=str(raw.get("detection_type") or ""),
                        detection=str(raw.get("detection") or ""),
                        text=str(raw.get("text") or ""),
                        score=raw.get("score", 0) or 0,
                        direction=direction,
                    )
                )
    warnings = body.get("warnings") or []
    flagged = bool(hits) or bool(warnings)
    if not flagged:
        return GuardrailsOutcome("", tuple(hits))
    choices = body.get("choices") or []
    action = "block" if not choices else "warn"
    return GuardrailsOutcome(action, tuple(hits))


def hit_reason(hit):
    """One human-readable line for a detector hit (SSE block body and Langfuse)."""
    try:
        score = float(hit.score)
        conf = f"{score:.1%}"
    except (TypeError, ValueError):
        conf = str(hit.score)
    label = hit.detection or hit.detector_id
    if hit.detector_id == "prompt_injection":
        return f"Prompt injection detected (confidence: {conf})"
    if hit.detection_type == "pii":
        return f'PII detected: {label} — "{hit.text}"'
    return f'Credential/secret detected: {label} — "{hit.text}"'


def blocked_message(hits):
    reasons = [hit_reason(h) for h in hits]
    if not reasons:
        reasons = ["Unsuitable input detected."]
    return "**Guardrails blocked your message.**\n\n" + "\n".join(f"- {r}" for r in reasons)


def record_outcome(outcome):
    """Increment the blocked-request counter for client-visible input skips."""
    global _blocked_total
    if outcome.action == "block":
        _blocked_total += 1


def metrics_text():
    return (
        "# HELP pca_guardrails_blocked_total "
        "Chat completions withheld from the LLM (empty choices).\n"
        "# TYPE pca_guardrails_blocked_total counter\n"
        f"pca_guardrails_blocked_total {_blocked_total}\n"
    )


def _langfuse_keys():
    return os.environ.get("LANGFUSE_PUBLIC_KEY") or "", os.environ.get(
        "LANGFUSE_SECRET_KEY"
    ) or ""


def _post_langfuse(payload):
    public_key, secret_key = _langfuse_keys()
    if not public_key or not secret_key:
        return
    auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    data = json.dumps(payload).encode("utf-8")
    req = Request(
        f"{LANGFUSE_BASE_URL}/api/public/ingestion",
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth}",
        },
    )
    try:
        with urlopen(req, timeout=10) as resp:
            resp.read()
    except (HTTPError, URLError, TimeoutError, OSError) as err:
        print(f"[proxy] Langfuse emit failed: {err}", flush=True)


def _extract_input(payload):
    if isinstance(payload, dict):
        if "messages" in payload:
            return payload["messages"]
        if "prompt" in payload:
            return payload["prompt"]
    return payload


def langfuse_flagged_batch(request_payload, orch_body, outcome, headers):
    """Build a Langfuse ingestion batch for a flagged (block or warn) outcome."""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    trace_id = str(uuid.uuid4())
    gen_id = str(uuid.uuid4())
    user_id = _header(headers, "X-PCA-User")
    devspace = _header(headers, "X-PCA-DevSpace")
    team = _header(headers, "X-PCA-Team")
    metadata = {
        "hits": [
            {
                "detector_id": h.detector_id,
                "detection_type": h.detection_type,
                "detection": h.detection,
                "text": h.text,
                "score": h.score,
                "direction": h.direction,
            }
            for h in outcome.hits
        ],
        "action": outcome.action,
    }
    if devspace:
        metadata["devspace"] = devspace
    if team:
        metadata["team"] = team
    tags = ["guardrails:flagged"]
    if outcome.action == "block":
        tags.append("guardrails:blocked")
    elif outcome.action == "warn":
        tags.append("guardrails:warned")
    if team:
        tags.append(f"team:{team}")
    if devspace:
        tags.append(f"devspace:{devspace}")
    if outcome.action == "block":
        output_data = blocked_message(outcome.hits)
    else:
        output_data = orch_body
    model = None
    if isinstance(request_payload, dict):
        model = request_payload.get("model")
    elif isinstance(orch_body, dict):
        model = orch_body.get("model")
    return {
        "batch": [
            {
                "id": str(uuid.uuid4()),
                "type": "trace-create",
                "timestamp": now,
                "body": {
                    "id": trace_id,
                    "name": "guardrails-flagged",
                    "userId": user_id,
                    "metadata": metadata,
                    "tags": tags,
                    "input": _extract_input(request_payload),
                    "output": output_data,
                    "timestamp": now,
                },
            },
            {
                "id": str(uuid.uuid4()),
                "type": "generation-create",
                "timestamp": now,
                "body": {
                    "id": gen_id,
                    "traceId": trace_id,
                    "name": "guardrails-flagged",
                    "model": model,
                    "input": _extract_input(request_payload),
                    "output": output_data,
                    "startTime": now,
                    "endTime": now,
                },
            },
        ]
    }


def schedule_flagged_langfuse(request_payload, orch_body, outcome, headers):
    public_key, secret_key = _langfuse_keys()
    if not public_key or not secret_key:
        return
    if not outcome.action:
        return
    payload = langfuse_flagged_batch(request_payload, orch_body, outcome, headers)
    _EMIT_POOL.submit(_post_langfuse, payload)


def observe_orchestrator_body(request_payload, orch_body, headers):
    """Record metrics and maybe emit Langfuse. Never raises to the caller."""
    try:
        outcome = parse_guardrails_outcome(orch_body)
        record_outcome(outcome)
        schedule_flagged_langfuse(request_payload, orch_body, outcome, headers)
        return outcome
    except Exception as err:
        print(f"[proxy] observe failed: {err}", flush=True)
        return GuardrailsOutcome("", ())


def _parse_json_bytes(raw):
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def completion_to_sse_chunks(body, outcome=None):
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

    if outcome is None:
        outcome = parse_guardrails_outcome(body)
    if outcome.action == "block":
        message = blocked_message(outcome.hits)
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
        observe_input = {k: body[k] for k in ("model", "messages", "prompt") if k in body}

        client_wants_stream = body.get("stream", False)

        body["detectors"] = DETECTORS
        body["stream"] = False
        body.pop("stream_options", None)
        body.setdefault("chat_template_kwargs", {})["enable_thinking"] = False

        target = f"{ORCHESTRATOR_URL}/api/v2/chat/completions-detection"
        req = Request(
            target,
            data=json.dumps(body).encode(),
            headers=_forward_pca_headers(self.headers),
            method="POST",
        )

        try:
            resp = urlopen(req, context=SSL_CTX)
            resp_body = resp.read()
            orch_json = _parse_json_bytes(resp_body)
            outcome = None
            if orch_json is not None:
                outcome = observe_orchestrator_body(observe_input, orch_json, self.headers)

            if client_wants_stream:
                resp_json = orch_json if orch_json is not None else json.loads(resp_body)
                sse = completion_to_sse_chunks(resp_json, outcome)
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
            orch_json = _parse_json_bytes(err_body)
            if orch_json is not None:
                observe_orchestrator_body(observe_input, orch_json, self.headers)
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
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            self.close_connection = True
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", "2")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(b"ok")
            return
        if path == "/metrics":
            self.close_connection = True
            payload = metrics_text().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)
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
    server = ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), ProxyHandler)
    server.daemon_threads = True
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
