"""
Guardrails Proxy — transparent OpenAI-compatible endpoint.

Accepts standard /v1/chat/completions requests from IDE extensions,
injects the configured detectors, and returns the response. Thinking is
forced off. Input skips are rewritten to a blocked SSE body so IDEs see
a clear message instead of empty choices.

Streaming chat does not go through TrustyAI's completion stream: that
path cannot parse vLLM qwen3_coder tool-call chunks. Input is probed with
max_tokens=0 (blocks skip the LLM; allowed requests get a fast vLLM 400),
then tokens stream from llm-d. Non-streaming JSON still uses TrustyAI.

Config via environment variables:
  ORCHESTRATOR_URL  — orchestrator base URL (default: https://pca-guardrails-service:8032)
  LLM_UPSTREAM_URL  — llm-d (or pca-semantic-router) base; required for streaming
  DETECTORS_JSON    — JSON detectors to inject into every request
  LISTEN_PORT       — port to listen on (default: 8080)
  LANGFUSE_BASE_URL / LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY
                    — optional; empty keys skip flagged-trace ingest
"""

from __future__ import annotations

import json
import os
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from guardrails_langfuse import langfuse_flagged_batch, schedule_flagged_langfuse
from guardrails_outcome import (
    GuardrailsOutcome,
    blocked_message,
    parse_guardrails_outcome,
)
from sse_http import (
    SSE_DONE,
    SSE_STREAM_BYTES,
    clip_sse_chunk,
    read_request_body,
    sse_content_length_pad,
    stream_sse_content_length,
)

ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "https://pca-guardrails-service:8032")
LLM_UPSTREAM_URL = os.environ.get("LLM_UPSTREAM_URL", "").rstrip("/")
DETECTORS = json.loads(os.environ.get("DETECTORS_JSON", "{}"))
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "8080"))

# Identity headers forwarded to the orchestrator / LLM for Langfuse attribution.
PCA_FORWARD_HEADERS = ("X-PCA-User", "X-PCA-Team", "X-PCA-DevSpace")

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

_blocked_total = 0
_overhead_lock = threading.Lock()
_overhead_seconds_total = 0.0


def _forward_pca_headers(incoming):
    """Copy X-PCA-* attribution headers from the client request."""
    out = {"Content-Type": "application/json"}
    for name in PCA_FORWARD_HEADERS:
        value = incoming.get(name)
        if value:
            out[name] = value
    return out


def record_outcome(outcome):
    """Increment the blocked-request counter for client-visible input skips."""
    global _blocked_total
    if outcome.action == "block":
        with _overhead_lock:
            _blocked_total += 1


def add_overhead_seconds(delta: float) -> None:
    """Add TrustyAI probe or SSE pad time. Excludes the llm-d token stream."""
    global _overhead_seconds_total
    if delta <= 0:
        return
    with _overhead_lock:
        _overhead_seconds_total += delta


def metrics_text():
    with _overhead_lock:
        blocked = _blocked_total
        overhead = _overhead_seconds_total
    return (
        "# HELP pca_guardrails_blocked_total "
        "Chat completions withheld from the LLM (empty choices).\n"
        "# TYPE pca_guardrails_blocked_total counter\n"
        f"pca_guardrails_blocked_total {blocked}\n"
        "# HELP pca_guardrails_overhead_seconds_total "
        "TrustyAI input probe plus SSE Content-Length pad. "
        "Excludes the llm-d token stream.\n"
        "# TYPE pca_guardrails_overhead_seconds_total counter\n"
        f"pca_guardrails_overhead_seconds_total {overhead}\n"
    )


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


def max_tokens_zero_rejected(status, err_body: bytes) -> bool:
    """True when vLLM rejected max_tokens=0 after TrustyAI input detectors passed."""
    if status != 400 or not err_body:
        return False
    return b"max_tokens must be at least 1" in err_body


def body_for_llm_upstream(body: dict) -> dict:
    """Client stream body for llm-d: no TrustyAI detectors, usage on the stream."""
    out = {k: v for k, v in body.items() if k != "detectors"}
    out["stream"] = True
    opts = out.get("stream_options")
    if not isinstance(opts, dict):
        opts = {}
        out["stream_options"] = opts
    opts["include_usage"] = True
    return out


def input_probe_body(orch_body: dict) -> dict:
    probe = dict(orch_body)
    probe["stream"] = False
    probe.pop("stream_options", None)
    probe["max_tokens"] = 0
    return probe


def completion_to_sse_chunks(body, outcome=None):
    """Convert a non-streaming chat completion to OpenAI-style SSE.

    AI SDK / OpenCode expect: role chunk, content or tool_calls, then an empty
    delta with finish_reason. Kuadrant token WASM looks for usage.total_tokens
    on the stream; omit it and Envoy never forwards the body.
    """
    chunks: list[str] = []
    created = body.get("created", int(time.time()))
    cid = body.get("id", "")
    model = body.get("model", "")
    usage = body.get("usage") or {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }

    def _event(choices, extra=None):
        payload = {
            "id": cid,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": choices,
        }
        if extra:
            payload.update(extra)
        chunks.append(f"data: {json.dumps(payload)}\n\n")

    if outcome is None:
        outcome = parse_guardrails_outcome(body)

    if outcome.action == "block":
        message = blocked_message(outcome.hits)
        _event(
            [
                {
                    "index": 0,
                    "delta": {"role": "assistant"},
                    "finish_reason": None,
                }
            ]
        )
        _event(
            [
                {
                    "index": 0,
                    "delta": {"content": message},
                    "finish_reason": None,
                }
            ]
        )
        _event(
            [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            extra={"usage": usage},
        )
        chunks.append("data: [DONE]\n\n")
        return "".join(chunks)

    for choice in body.get("choices", []):
        msg = choice.get("message") or {}
        idx = choice.get("index", 0)
        _event(
            [
                {
                    "index": idx,
                    "delta": {"role": msg.get("role", "assistant")},
                    "finish_reason": None,
                }
            ]
        )
        content = msg.get("content") or ""
        if content:
            _event(
                [
                    {
                        "index": idx,
                        "delta": {"content": content},
                        "finish_reason": None,
                    }
                ]
            )
        tool_calls = msg.get("tool_calls") or []
        if tool_calls:
            deltas = []
            for i, tc in enumerate(tool_calls):
                if not isinstance(tc, dict):
                    continue
                deltas.append(
                    {
                        "index": i,
                        "id": tc.get("id"),
                        "type": tc.get("type", "function"),
                        "function": tc.get("function") or {},
                    }
                )
            if deltas:
                _event(
                    [
                        {
                            "index": idx,
                            "delta": {"tool_calls": deltas},
                            "finish_reason": None,
                        }
                    ]
                )
        finish = choice.get("finish_reason") or (
            "tool_calls" if tool_calls else "stop"
        )
        _event(
            [{"index": idx, "delta": {}, "finish_reason": finish}],
            extra={"usage": usage},
        )

    chunks.append("data: [DONE]\n\n")
    return "".join(chunks)


def _flatten_content(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                texts.append(str(part.get("text") or part.get("content") or ""))
            elif part is not None:
                texts.append(str(part))
        return "".join(texts)
    return str(content)


def normalize_orchestrator_messages(body: dict) -> dict:
    """TrustyAI rejects array content and role=tool (422). Flatten for detection.

    Returns a shallow copy. The llm-d body must keep role=tool / array content.
    """
    messages = body.get("messages")
    if not isinstance(messages, list):
        return body
    out = []
    for raw in messages:
        if not isinstance(raw, dict):
            continue
        msg = dict(raw)
        msg["content"] = _flatten_content(msg.get("content"))
        if msg.get("role") == "tool":
            tid = msg.pop("tool_call_id", None) or ""
            name = msg.pop("name", "") or ""
            bits = ["[tool result"]
            if name:
                bits.append(str(name))
            if tid:
                bits.append(str(tid))
            msg["role"] = "user"
            msg["content"] = " ".join(bits) + "]\n" + msg["content"]
            msg.pop("tool_calls", None)
        out.append(msg)
    copy = dict(body)
    copy["messages"] = out
    return copy


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _write_payload(self, status: int, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def _write_sse_bytes(self, sse_bytes: bytes) -> None:
        # Blocked replies are a complete body. Content-Length is safe here and
        # avoids Envoy's HTTP/1.1 chunked truncation when last-chunk is lost.
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(sse_bytes)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(sse_bytes)

    def _stream_sse_content_length(self, resp) -> None:
        stream_sse_content_length(
            self, resp, cap=SSE_STREAM_BYTES, on_pad=add_overhead_seconds
        )

    def _write_blocked_sse(self, orch_json, outcome):
        self._write_sse_bytes(completion_to_sse_chunks(orch_json, outcome).encode())

    def _stream_via_input_probe(self, orch_body, observe_input, llm_body):
        """Block on input detectors, then stream tokens from llm-d (not TrustyAI)."""
        probe = input_probe_body(orch_body)
        target = f"{ORCHESTRATOR_URL}/api/v2/chat/completions-detection"
        req = Request(
            target,
            data=json.dumps(probe).encode(),
            headers=_forward_pca_headers(self.headers),
            method="POST",
        )
        t0 = time.monotonic()
        try:
            resp = urlopen(req, context=SSL_CTX)
            orch_json = _parse_json_bytes(resp.read())
        except HTTPError as e:
            err_body = e.read()
            add_overhead_seconds(time.monotonic() - t0)
            if max_tokens_zero_rejected(e.code, err_body):
                self._stream_llm_upstream(llm_body)
                return
            orch_json = _parse_json_bytes(err_body)
            if orch_json is not None:
                observe_orchestrator_body(observe_input, orch_json, self.headers)
            self._write_payload(e.code, err_body, "application/json")
            return
        except URLError as e:
            add_overhead_seconds(time.monotonic() - t0)
            err = json.dumps({"error": str(e.reason)}).encode()
            self._write_payload(502, err, "application/json")
            return
        add_overhead_seconds(time.monotonic() - t0)
        outcome = None
        if orch_json is not None:
            outcome = observe_orchestrator_body(observe_input, orch_json, self.headers)
        if outcome is not None and outcome.action == "block":
            self._write_blocked_sse(orch_json, outcome)
            return
        self._stream_llm_upstream(llm_body)

    def _stream_llm_upstream(self, body):
        payload = json.dumps(body_for_llm_upstream(body)).encode()
        url = f"{LLM_UPSTREAM_URL}/v1/chat/completions"
        req = Request(
            url,
            data=payload,
            headers=_forward_pca_headers(self.headers),
            method="POST",
        )
        kwargs = {"context": SSL_CTX} if url.startswith("https") else {}
        try:
            resp = urlopen(req, **kwargs)
            self._stream_sse_content_length(resp)
        except HTTPError as e:
            self._write_payload(e.code, e.read(), "application/json")
        except URLError as e:
            err = json.dumps({"error": str(e.reason)}).encode()
            self._write_payload(502, err, "application/json")
        except BrokenPipeError:
            return

    def do_POST(self):
        self.close_connection = True
        raw = read_request_body(self.headers, self.rfile)
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            err = json.dumps({"error": "invalid JSON body"}).encode()
            self._write_payload(400, err, "application/json")
            return
        if not isinstance(body, dict):
            body = {}
        original = body
        body = normalize_orchestrator_messages(body)
        observe_input = {k: body[k] for k in ("model", "messages", "prompt") if k in body}

        client_wants_stream = bool(original.get("stream", False))

        body["detectors"] = DETECTORS
        body.setdefault("chat_template_kwargs", {})["enable_thinking"] = False
        if not client_wants_stream:
            body["stream"] = False
            body.pop("stream_options", None)

        if client_wants_stream:
            if not LLM_UPSTREAM_URL:
                err = json.dumps(
                    {"error": "LLM_UPSTREAM_URL is required for streaming"}
                ).encode()
                self._write_payload(503, err, "application/json")
                return
            llm_body = dict(original)
            kwargs = dict(llm_body.get("chat_template_kwargs") or {})
            kwargs["enable_thinking"] = False
            llm_body["chat_template_kwargs"] = kwargs
            self._stream_via_input_probe(body, observe_input, llm_body)
            return

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
            if orch_json is not None:
                observe_orchestrator_body(observe_input, orch_json, self.headers)
            self._write_payload(
                resp.status, resp_body, "application/json"
            )
        except HTTPError as e:
            err_body = e.read()
            orch_json = _parse_json_bytes(err_body)
            if orch_json is not None:
                observe_orchestrator_body(observe_input, orch_json, self.headers)
            self._write_payload(e.code, err_body, "application/json")
        except URLError as e:
            err = json.dumps({"error": str(e.reason)}).encode()
            self._write_payload(502, err, "application/json")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            self.close_connection = True
            self._write_payload(200, b"ok", "text/plain")
            return
        if path == "/metrics":
            self.close_connection = True
            self._write_payload(
                200,
                metrics_text().encode(),
                "text/plain; version=0.0.4; charset=utf-8",
            )
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
            self._write_payload(502, b"", "text/plain")

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
