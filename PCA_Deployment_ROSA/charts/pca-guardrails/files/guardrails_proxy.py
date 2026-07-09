"""
Guardrails Proxy — transparent OpenAI-compatible endpoint.

Accepts standard /v1/chat/completions requests from IDE extensions,
injects the configured detectors, forwards to the TrustyAI orchestrator
detection API, and returns the response unchanged (no response parsing).

Config via environment variables:
  ORCHESTRATOR_URL  — orchestrator base URL (default: https://pca-guardrails-service:8032)
  DETECTORS_JSON    — JSON detectors to inject into every request
  LISTEN_PORT       — port to listen on (default: 8080)
"""
import json
import os
import ssl
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

ORCHESTRATOR_URL = os.environ.get(
    "ORCHESTRATOR_URL", "https://pca-guardrails-service:8032"
)
DETECTORS = json.loads(os.environ.get("DETECTORS_JSON", "{}"))
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "8080"))

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


class ProxyHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        body["detectors"] = DETECTORS

        target = f"{ORCHESTRATOR_URL}/api/v2/chat/completions-detection"
        req = Request(
            target,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            resp = urlopen(req, context=SSL_CTX)
            self.send_response(resp.status)
            for key in ("content-type", "content-length"):
                val = resp.headers.get(key)
                if val:
                    self.send_header(key, val)
            self.end_headers()
            self.wfile.write(resp.read())
        except HTTPError as e:
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(e.read())
        except URLError as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e.reason)}).encode())

    def do_GET(self):
        if self.path == "/healthz":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
            return
        target = f"{ORCHESTRATOR_URL}{self.path}"
        req = Request(target, method="GET")
        try:
            resp = urlopen(req, context=SSL_CTX)
            self.send_response(resp.status)
            self.send_header("Content-Type", resp.headers.get("content-type", "application/json"))
            self.end_headers()
            self.wfile.write(resp.read())
        except (HTTPError, URLError) as e:
            self.send_response(502)
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
