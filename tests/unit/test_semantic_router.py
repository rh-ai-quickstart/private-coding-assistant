"""Unit tests for the Semantic Router hop decide() helper."""

from __future__ import annotations

import http.client
import importlib.util
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "charts"
    / "pca-ai-serving"
    / "charts"
    / "pca-semantic-router"
    / "files"
    / "semantic_router.py"
)


def _load():
    files_dir = str(_MODULE_PATH.parent)
    sys.modules.pop("sse_http", None)
    if files_dir not in sys.path:
        sys.path.insert(0, files_dir)
    spec = importlib.util.spec_from_file_location("pca_semantic_router", _MODULE_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pca_semantic_router"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_pin_local_even_with_external_configured():
    sr = _load()
    body = {"model": "gpt-4o", "messages": [{"role": "user", "content": "hello"}]}
    assert (
        sr.decide(
            body,
            route_mode="pin-local",
            external_base="https://api.openai.com/v1",
            external_api_key="sk-test",
            external_models={"gpt-4o"},
        )
        == "local"
    )


def test_auto_without_key_stays_local():
    sr = _load()
    body = {"messages": [{"role": "user", "content": "write a haiku"}]}
    assert (
        sr.decide(
            body,
            route_mode="auto",
            external_base="https://api.openai.com/v1",
            external_api_key="",
        )
        == "local"
    )


def test_auto_named_external_model():
    sr = _load()
    body = {"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]}
    assert (
        sr.decide(
            body,
            route_mode="auto",
            external_base="https://api.openai.com/v1",
            external_api_key="sk-test",
            external_models={"gpt-4o"},
        )
        == "external"
    )


def test_auto_code_keyword_stays_local():
    sr = _load()
    body = {
        "model": "anything",
        "messages": [{"role": "user", "content": "implement a python function"}],
    }
    assert (
        sr.decide(
            body,
            route_mode="auto",
            external_base="https://api.openai.com/v1",
            external_api_key="sk-test",
            auto_keywords=("code", "function", "python"),
        )
        == "local"
    )


def test_auto_non_code_goes_external():
    sr = _load()
    body = {"messages": [{"role": "user", "content": "what is the capital of france"}]}
    assert (
        sr.decide(
            body,
            route_mode="auto",
            external_base="https://api.openai.com/v1",
            external_api_key="sk-test",
            auto_keywords=("code", "function"),
        )
        == "external"
    )


def test_split_local_upstream_tokenize_uses_vllm_root():
    sr = _load()
    base = "http://llm-d.svc:80/v1"
    assert sr.split_local_upstream(base, "/tokenize") == (
        "http://llm-d.svc:80",
        "/tokenize",
    )
    assert sr.split_local_upstream(base, "/v1/tokenize") == (
        "http://llm-d.svc:80",
        "/tokenize",
    )
    assert sr.split_local_upstream(base, "/v1/chat/completions") == (
        "http://llm-d.svc:80/v1",
        "/chat/completions",
    )


def test_post_tokenize_does_not_prefix_v1(monkeypatch):
    seen: list[str] = []

    class _Tok(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            return

        def do_POST(self):
            seen.append(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            payload = b'{"tokens":[1]}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    upstream = _serve(_Tok)
    router = None
    try:
        monkeypatch.setenv(
            "LOCAL_BASE_URL", f"http://127.0.0.1:{upstream.server_port}/v1"
        )
        sr = _load()
        router = _serve(sr.Handler)
        conn = http.client.HTTPConnection(
            "127.0.0.1", router.server_port, timeout=5
        )
        conn.request(
            "POST",
            "/tokenize",
            body=b'{"model":"Qwen/Qwen3.6-35B-A3B-FP8"}',
            headers={"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
    finally:
        if router is not None:
            router.shutdown()
            router.server_close()
        upstream.shutdown()
        upstream.server_close()
    assert resp.status == 200, body
    assert seen == ["/tokenize"]


def test_read_request_body_content_length():
    sr = _load()
    raw = b'{"model":"x"}'
    headers = {"Content-Length": str(len(raw))}
    from io import BytesIO

    assert sr.read_request_body(headers, BytesIO(raw)) == raw


def test_read_request_body_chunked():
    sr = _load()
    from io import BytesIO

    payload = b'{"messages":[{"role":"user","content":"hi"}]}'
    chunked = f"{len(payload):x}\r\n".encode() + payload + b"\r\n0\r\n\r\n"
    headers = {"Transfer-Encoding": "chunked"}
    assert sr.read_request_body(headers, BytesIO(chunked)) == payload


def test_read_request_body_empty():
    sr = _load()
    from io import BytesIO

    assert sr.read_request_body({}, BytesIO(b"")) == b""


def _serve(handler_cls) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class _OkUpstream(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        return

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        payload = b'{"choices":[]}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


_SLOW_SECS = 0.3
_FIRST_SSE = b'data: {"choices":[{"delta":{"content":"a"}}]}\n\n'
_LAST_SSE = b"data: [DONE]\n\n"


def _slow_upstream(last_write_at: list[float]):
    class _Slow(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            return

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(_FIRST_SSE) + len(_LAST_SSE)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(_FIRST_SSE)
            self.wfile.flush()
            time.sleep(_SLOW_SECS)
            self.wfile.write(_LAST_SSE)
            self.wfile.flush()
            last_write_at.append(time.monotonic())

    return _Slow


def test_decide_called_once_per_post(monkeypatch):
    upstream = _serve(_OkUpstream)
    router = None
    try:
        monkeypatch.setenv(
            "LOCAL_BASE_URL", f"http://127.0.0.1:{upstream.server_port}/v1"
        )
        sr = _load()
        calls: list[object] = []
        real = sr.decide

        def _count(body, **kwargs):
            calls.append(1)
            return real(body, **kwargs)

        monkeypatch.setattr(sr, "decide", _count)
        router = _serve(sr.Handler)
        payload = b'{"messages":[{"role":"user","content":"hi"}]}'
        conn = http.client.HTTPConnection(
            "127.0.0.1", router.server_port, timeout=5
        )
        conn.request(
            "POST",
            "/v1/chat/completions",
            body=payload,
            headers={"Content-Type": "application/json"},
        )
        conn.getresponse().read()
        conn.close()
    finally:
        if router is not None:
            router.shutdown()
            router.server_close()
        upstream.shutdown()
        upstream.server_close()
    assert len(calls) == 1


def test_stream_first_byte_before_upstream_last_write(monkeypatch):
    last_write_at: list[float] = []
    upstream = _serve(_slow_upstream(last_write_at))
    router = None
    try:
        monkeypatch.setenv(
            "LOCAL_BASE_URL", f"http://127.0.0.1:{upstream.server_port}/v1"
        )
        sr = _load()
        router = _serve(sr.Handler)
        payload = json.dumps(
            {"stream": True, "messages": [{"role": "user", "content": "hi"}]}
        ).encode()
        conn = http.client.HTTPConnection(
            "127.0.0.1", router.server_port, timeout=10
        )
        conn.request(
            "POST",
            "/v1/chat/completions",
            body=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        first = resp.read(1)
        client_first_byte_at = time.monotonic()
        while resp.read(4096):
            pass
        conn.close()
    finally:
        if router is not None:
            router.shutdown()
            router.server_close()
        upstream.shutdown()
        upstream.server_close()
    assert first
    assert last_write_at
    assert client_first_byte_at < last_write_at[0]


def test_hop_seconds_exclude_token_stream(monkeypatch):
    last_write_at: list[float] = []
    upstream = _serve(_slow_upstream(last_write_at))
    router = None
    try:
        monkeypatch.setenv(
            "LOCAL_BASE_URL", f"http://127.0.0.1:{upstream.server_port}/v1"
        )
        sr = _load()
        router = _serve(sr.Handler)
        payload = json.dumps(
            {"stream": True, "messages": [{"role": "user", "content": "hi"}]}
        ).encode()
        conn = http.client.HTTPConnection(
            "127.0.0.1", router.server_port, timeout=10
        )
        conn.request(
            "POST",
            "/v1/chat/completions",
            body=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        while resp.read(4096):
            pass
        conn.close()
        hop = sr._hop_seconds_total
    finally:
        if router is not None:
            router.shutdown()
            router.server_close()
        upstream.shutdown()
        upstream.server_close()
    assert last_write_at
    assert 0 < hop < 0.15
    assert "pca_semantic_router_hop_seconds_total" in sr.metrics_text()
