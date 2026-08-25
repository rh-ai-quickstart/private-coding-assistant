"""OpenAI-compatible hop that picks local llm-d or an external provider.

API-mode stand-in for vLLM Semantic Router (HTTP, not Envoy ExtProc).
Swap the Deployment image later if the full classifier stack is required.
"""

from __future__ import annotations

import io
import json
import os
import ssl
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sse_http import SSE_STREAM_BYTES, read_request_body, stream_sse_content_length

LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "8080"))
LOCAL_BASE = os.environ.get("LOCAL_BASE_URL", "http://127.0.0.1:80/v1").rstrip("/")
EXTERNAL_BASE = os.environ.get("EXTERNAL_BASE_URL", "").rstrip("/")
EXTERNAL_API_KEY = os.environ.get("EXTERNAL_API_KEY", "")
LOCAL_MODEL = os.environ.get("LOCAL_MODEL", "")
EXTERNAL_MODELS = {
    m.strip()
    for m in os.environ.get("EXTERNAL_MODELS", "").split(",")
    if m.strip()
}
ROUTE_MODE = os.environ.get("ROUTE_MODE", "pin-local")
AUTO_KEYWORDS = tuple(
    k.strip().lower()
    for k in os.environ.get(
        "AUTO_KEYWORDS",
        "code,function,class,implement,refactor,debug,complete,python,javascript,typescript,golang,rust",
    ).split(",")
    if k.strip()
)

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

_STATE_LOCK = threading.Lock()
_decisions = {"local": 0, "external": 0}
_hop_seconds_total = 0.0


class _SupportsRead(Protocol):
    def read(self, n: int = -1) -> bytes: ...


@dataclass(frozen=True)
class _UpstreamResponse:
    status: int
    content_type: str
    body: _SupportsRead


def last_user_text(body: dict) -> str:
    messages = body.get("messages") or []
    if not isinstance(messages, list):
        return str(body.get("prompt") or "")
    for msg in reversed(messages):
        if not isinstance(msg, dict):
            continue
        if msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, str):
                return content
            return str(content or "")
    return str(body.get("prompt") or "")


def decide(
    body: dict,
    *,
    route_mode: str | None = None,
    external_base: str | None = None,
    external_api_key: str | None = None,
    local_model: str | None = None,
    external_models: set[str] | None = None,
    auto_keywords: tuple[str, ...] | None = None,
) -> str:
    """Return 'local' or 'external'."""
    mode = route_mode if route_mode is not None else ROUTE_MODE
    ext_base = EXTERNAL_BASE if external_base is None else external_base
    ext_key = EXTERNAL_API_KEY if external_api_key is None else external_api_key
    loc_model = LOCAL_MODEL if local_model is None else local_model
    ext_models = EXTERNAL_MODELS if external_models is None else external_models
    keywords = AUTO_KEYWORDS if auto_keywords is None else auto_keywords
    if mode != "auto" or not ext_base or not ext_key:
        return "local"
    model = str(body.get("model") or "")
    if loc_model and model == loc_model:
        return "local"
    if model in ext_models:
        return "external"
    text = last_user_text(body).lower()
    if any(k in text for k in keywords):
        return "local"
    return "external"


def record_decision(backend: str) -> None:
    with _STATE_LOCK:
        _decisions[backend] = _decisions.get(backend, 0) + 1


def add_hop_seconds(delta: float) -> None:
    global _hop_seconds_total
    if delta <= 0:
        return
    with _STATE_LOCK:
        _hop_seconds_total += delta


def metrics_text() -> str:
    with _STATE_LOCK:
        local = _decisions.get("local", 0)
        external = _decisions.get("external", 0)
        hop = _hop_seconds_total
    return (
        "# HELP pca_semantic_router_decisions_total Routed chat completions\n"
        "# TYPE pca_semantic_router_decisions_total counter\n"
        f'pca_semantic_router_decisions_total{{backend="local"}} {local}\n'
        f'pca_semantic_router_decisions_total{{backend="external"}} {external}\n'
        "# HELP pca_semantic_router_hop_seconds_total "
        "Parse, decide, connect, and upstream headers. Excludes the token stream.\n"
        "# TYPE pca_semantic_router_hop_seconds_total counter\n"
        f"pca_semantic_router_hop_seconds_total {hop}\n"
    )


def _close_body(body: _SupportsRead) -> None:
    close = getattr(body, "close", None)
    if close is not None:
        close()


def _forward_stream(
    base: str, path: str, method: str, body: bytes | None, headers: dict
) -> _UpstreamResponse:
    url = f"{base}{path}"
    req = Request(url, data=body, method=method)
    for key, value in headers.items():
        req.add_header(key, value)
    ctx = SSL_CTX if url.startswith("https://") else None
    try:
        resp = urlopen(req, context=ctx, timeout=600)
        ctype = resp.headers.get("Content-Type") or "application/json"
        return _UpstreamResponse(resp.status, ctype, resp)
    except HTTPError as err:
        try:
            payload = err.read()
        finally:
            err.close()
        ctype = err.headers.get("Content-Type") or "application/json"
        return _UpstreamResponse(err.code, ctype, io.BytesIO(payload))
    except URLError as err:
        payload = json.dumps(
            {"error": {"message": str(err.reason), "type": "router_upstream"}}
        ).encode()
        return _UpstreamResponse(502, "application/json", io.BytesIO(payload))


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        return

    def _write(self, status: int, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _stream_sse_content_length(self, body: _SupportsRead, backend: str) -> None:
        stream_sse_content_length(
            self,
            body,
            cap=SSE_STREAM_BYTES,
            extra_headers={"X-PCA-Route-Backend": backend},
            on_pad=add_hop_seconds,
        )

    def do_GET(self):
        if self.path in ("/healthz", "/readyz"):
            self._write(200, b"ok", "text/plain")
            return
        if self.path == "/metrics":
            self._write(200, metrics_text().encode(), "text/plain; version=0.0.4")
            return
        if self.path.startswith("/v1/"):
            upstream = _forward_stream(LOCAL_BASE, self.path[3:], "GET", None, {})
            try:
                self._write(
                    upstream.status, upstream.body.read(), upstream.content_type
                )
            finally:
                _close_body(upstream.body)
            return
        self._write(404, b"not found", "text/plain")

    def do_POST(self):
        raw = read_request_body(self.headers, self.rfile)
        try:
            body = json.loads(raw.decode() or "{}") if raw else {}
        except json.JSONDecodeError:
            self._write(400, b'{"error":{"message":"invalid json"}}', "application/json")
            return
        if not isinstance(body, dict):
            body = {}
        t0 = time.monotonic()
        backend = decide(body)
        record_decision(backend)
        if backend == "external":
            base = EXTERNAL_BASE
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {EXTERNAL_API_KEY}",
            }
        else:
            base = LOCAL_BASE
            headers = {"Content-Type": "application/json"}
        path = self.path[3:] if self.path.startswith("/v1") else self.path
        if not path.startswith("/"):
            path = f"/{path}"
        upstream = _forward_stream(
            base, path, "POST", json.dumps(body).encode(), headers
        )
        add_hop_seconds(time.monotonic() - t0)
        try:
            if body.get("stream") is True and upstream.status == 200:
                self._stream_sse_content_length(upstream.body, backend)
                return
            data = upstream.body.read()
            self.send_response(upstream.status)
            self.send_header("Content-Type", upstream.content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-PCA-Route-Backend", backend)
            self.end_headers()
            self.wfile.write(data)
        finally:
            _close_body(upstream.body)


def main():
    server = ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
