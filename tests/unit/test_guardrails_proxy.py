"""Unit tests for guardrails proxy outcome parsing, metrics, and Langfuse batch."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "charts"
    / "pca-ai-serving"
    / "charts"
    / "pca-guardrails"
    / "files"
    / "guardrails_proxy.py"
)

INPUT_SKIP = {
    "choices": [],
    "detections": {
        "input": [
            {
                "message_index": 0,
                "results": [
                    {
                        "detector_id": "prompt_injection",
                        "detection_type": "security",
                        "text": "ignore previous",
                        "score": 0.9,
                    }
                ],
            }
        ]
    },
    "warnings": [{"type": "UNSUITABLE_INPUT", "message": "Unsuitable input detected."}],
}

OUTPUT_FLAG = {
    "choices": [{"message": {"role": "assistant", "content": "print(1)"}}],
    "detections": {
        "output": [
            {
                "results": [
                    {
                        "detector_id": "regex",
                        "detection_type": "pii",
                        "detection": "email",
                        "text": "a@b.c",
                        "score": 1.0,
                    }
                ]
            }
        ]
    },
    "warnings": [{"type": "UNSUITABLE_OUTPUT"}],
}

ALLOWED = {
    "choices": [{"message": {"role": "assistant", "content": "hello"}}],
}


@pytest.fixture
def proxy():
    files_dir = str(_MODULE_PATH.parent)
    for name in ("sse_http", "guardrails_outcome", "guardrails_langfuse"):
        sys.modules.pop(name, None)
    if files_dir not in sys.path:
        sys.path.insert(0, files_dir)
    spec = importlib.util.spec_from_file_location("guardrails_proxy", _MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["guardrails_proxy"] = module
    spec.loader.exec_module(module)
    module._blocked_total = 0
    module._overhead_seconds_total = 0.0
    yield module
    module._blocked_total = 0
    module._overhead_seconds_total = 0.0


def test_parse_input_skip_is_block(proxy):
    outcome = proxy.parse_guardrails_outcome(INPUT_SKIP)
    assert outcome.action == "block"
    assert len(outcome.hits) == 1
    assert outcome.hits[0].detector_id == "prompt_injection"
    assert outcome.hits[0].direction == "input"


def test_parse_output_flag_is_warn(proxy):
    outcome = proxy.parse_guardrails_outcome(OUTPUT_FLAG)
    assert outcome.action == "warn"
    assert outcome.hits[0].detection_type == "pii"
    assert outcome.hits[0].direction == "output"


def test_parse_allowed_is_empty_action(proxy):
    outcome = proxy.parse_guardrails_outcome(ALLOWED)
    assert outcome.action == ""
    assert outcome.hits == ()


def test_parse_non_dict_is_allowed(proxy):
    assert proxy.parse_guardrails_outcome(None).action == ""
    assert proxy.parse_guardrails_outcome([]).action == ""


def test_record_outcome_counts_only_blocks(proxy):
    proxy.record_outcome(proxy.parse_guardrails_outcome(ALLOWED))
    proxy.record_outcome(proxy.parse_guardrails_outcome(OUTPUT_FLAG))
    assert proxy._blocked_total == 0
    proxy.record_outcome(proxy.parse_guardrails_outcome(INPUT_SKIP))
    proxy.record_outcome(proxy.parse_guardrails_outcome(INPUT_SKIP))
    assert proxy._blocked_total == 2
    text = proxy.metrics_text()
    assert "pca_guardrails_blocked_total 2" in text
    assert "# TYPE pca_guardrails_blocked_total counter" in text
    assert "pca_guardrails_overhead_seconds_total 0.0" in text
    assert "# TYPE pca_guardrails_overhead_seconds_total counter" in text


def test_sse_block_uses_outcome_hits(proxy):
    sse = proxy.completion_to_sse_chunks(INPUT_SKIP)
    assert "Guardrails blocked your message" in sse
    assert "Prompt injection detected" in sse
    assert "data: [DONE]" in sse
    assert '"total_tokens": 0' in sse
    assert '"finish_reason": "stop"' in sse


def test_sse_output_flag_keeps_model_text(proxy):
    sse = proxy.completion_to_sse_chunks(OUTPUT_FLAG)
    assert "print(1)" in sse
    assert "Guardrails blocked your message" not in sse


def test_sse_includes_usage_and_empty_finish_delta(proxy):
    body = {
        "id": "cmpl-1",
        "model": "m",
        "choices": [{"message": {"role": "assistant", "content": "hi"}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
    }
    sse = proxy.completion_to_sse_chunks(body)
    assert '"total_tokens": 4' in sse
    assert '"delta": {}' in sse
    assert "data: [DONE]" in sse


def test_sse_forwards_tool_calls(proxy):
    body = {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "edit", "arguments": "{}"},
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    sse = proxy.completion_to_sse_chunks(body)
    assert "call_1" in sse
    assert '"name": "edit"' in sse
    assert '"finish_reason": "tool_calls"' in sse


def test_normalize_flattens_array_content_and_tool_role(proxy):
    body = {
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": "edit calculator.py"}],
            },
            {
                "role": "tool",
                "tool_call_id": "c1",
                "name": "edit",
                "content": "ok",
            },
        ]
    }
    out = proxy.normalize_orchestrator_messages(body)["messages"]
    assert out[0]["content"] == "edit calculator.py"
    assert out[1]["role"] == "user"
    assert "c1" in out[1]["content"]
    assert out[1]["content"].endswith("ok")


def test_langfuse_batch_tags_blocked(proxy):
    outcome = proxy.parse_guardrails_outcome(INPUT_SKIP)
    payload = proxy.langfuse_flagged_batch(
        {"model": "m", "messages": [{"role": "user", "content": "jailbreak"}]},
        INPUT_SKIP,
        outcome,
        {"X-PCA-User": "dev-user1", "X-PCA-DevSpace": "dev-user1-devspaces"},
    )
    traces = [e for e in payload["batch"] if e["type"] == "trace-create"]
    assert len(traces) == 1
    body = traces[0]["body"]
    assert body["name"] == "guardrails-flagged"
    assert body["userId"] == "dev-user1"
    assert "guardrails:flagged" in body["tags"]
    assert "guardrails:blocked" in body["tags"]
    assert "devspace:dev-user1-devspaces" in body["tags"]
    assert "jailbreak" in json.dumps(body["input"])
    assert "Guardrails blocked" in body["output"]
    assert body["metadata"]["action"] == "block"
    assert body["metadata"]["hits"][0]["detector_id"] == "prompt_injection"


def test_langfuse_batch_tags_warned(proxy):
    outcome = proxy.parse_guardrails_outcome(OUTPUT_FLAG)
    payload = proxy.langfuse_flagged_batch(
        {"messages": [{"role": "user", "content": "write code"}]},
        OUTPUT_FLAG,
        outcome,
        {},
    )
    body = payload["batch"][0]["body"]
    assert "guardrails:warned" in body["tags"]
    assert "guardrails:blocked" not in body["tags"]


def test_schedule_langfuse_skips_without_keys(proxy):
    import guardrails_langfuse as lf

    outcome = proxy.parse_guardrails_outcome(INPUT_SKIP)
    with patch.dict("os.environ", {"LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": ""}, clear=False):
        with patch.object(lf, "_EMIT_POOL") as pool:
            proxy.schedule_flagged_langfuse({}, INPUT_SKIP, outcome, {})
            pool.submit.assert_not_called()


def test_schedule_langfuse_skips_allowed(proxy, monkeypatch):
    import guardrails_langfuse as lf

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    outcome = proxy.parse_guardrails_outcome(ALLOWED)
    with patch.object(lf, "_EMIT_POOL") as pool:
        proxy.schedule_flagged_langfuse({}, ALLOWED, outcome, {})
        pool.submit.assert_not_called()


def test_read_request_body_content_length(proxy):
    raw = b'{"model":"x"}'
    headers = {"Content-Length": str(len(raw))}
    from io import BytesIO

    assert proxy.read_request_body(headers, BytesIO(raw)) == raw


def test_read_request_body_chunked(proxy):
    from io import BytesIO

    payload = b'{"messages":[{"role":"user","content":"hi"}]}'
    chunked = f"{len(payload):x}\r\n".encode() + payload + b"\r\n0\r\n\r\n"
    headers = {"Transfer-Encoding": "chunked"}
    assert proxy.read_request_body(headers, BytesIO(chunked)) == payload


def test_read_request_body_empty(proxy):
    from io import BytesIO

    assert proxy.read_request_body({}, BytesIO(b"")) == b""


def test_max_tokens_zero_rejected(proxy):
    details = b'{"code":400,"details":"max_tokens must be at least 1, got 0."}'
    assert proxy.max_tokens_zero_rejected(400, details) is True
    assert proxy.max_tokens_zero_rejected(400, b'{"code":400,"details":"bad request"}') is False
    assert proxy.max_tokens_zero_rejected(422, details) is False
    assert proxy.max_tokens_zero_rejected(400, b"") is False


def test_body_for_llm_upstream_strips_detectors(proxy):
    body = {
        "model": "m",
        "messages": [{"role": "user", "content": "hi"}],
        "detectors": {"regex": {}},
        "stream": False,
        "max_tokens": 64,
    }
    out = proxy.body_for_llm_upstream(body)
    assert "detectors" not in out
    assert out["stream"] is True
    assert out["stream_options"]["include_usage"] is True
    assert out["max_tokens"] == 64
    assert body["detectors"] == {"regex": {}}


class _FakeUpstream:
    def __init__(self, data: bytes, size: int = 4096) -> None:
        self._data = data
        self._size = size

    def read(self, n: int = -1) -> bytes:
        if not self._data:
            return b""
        take = len(self._data) if n < 0 else min(n, self._size, len(self._data))
        out, self._data = self._data[:take], self._data[take:]
        return out


class _FakeHandler:
    def __init__(self) -> None:
        from io import BytesIO

        self.status = None
        self.headers: list[tuple[str, str]] = []
        self.wfile = BytesIO()

    def send_response(self, code: int) -> None:
        self.status = code

    def send_header(self, key: str, value: str) -> None:
        self.headers.append((key, value))

    def end_headers(self) -> None:
        return


def test_normalize_does_not_mutate_tool_messages(proxy):
    body = {
        "model": "m",
        "stream": True,
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "edit", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "c1",
                "name": "edit",
                "content": "ok",
            },
        ],
    }
    out = proxy.normalize_orchestrator_messages(body)
    assert body["messages"][-1]["role"] == "tool"
    assert out["messages"][-1]["role"] == "user"
    assert "c1" in out["messages"][-1]["content"]
    llm = proxy.body_for_llm_upstream(body)
    assert llm["messages"][-1]["role"] == "tool"


def test_sse_content_length_pad_is_one_comment(proxy):
    for remain in (0, 1, 2, 3, 4, 256, 256 * 1024):
        pad = proxy.sse_content_length_pad(remain)
        assert len(pad) == remain
        if remain >= 3:
            assert pad.startswith(b":")
            assert pad.endswith(b"\n\n")
            assert pad.count(b"\n\n") == 1


def test_proxy_raw_sse_declares_content_length_then_streams(proxy):
    """OpenCode speaks HTTP/1.1. Envoy truncates chunked/identity SSE.
    Content-Length must be declared before upstream finishes, and the
    body length must match so the client sees a complete stream.
    """
    from types import MethodType

    first = b'data: {"choices":[{"delta":{"content":"p"}}]}\n\n'
    rest = (
        b'data: {"choices":[{"delta":{"content":"ong"}}]}\n\n'
        b"data: [DONE]\n\n"
    )
    cap = 256
    old_cap = proxy.SSE_STREAM_BYTES
    proxy.SSE_STREAM_BYTES = cap
    mid = {}

    class _GatedUpstream:
        def __init__(self) -> None:
            self.parts = [first, rest]
            self.i = 0

        def read(self, n: int = -1) -> bytes:
            if self.i == 1:
                mid["status"] = handler.status
                mid["headers"] = dict(handler.headers)
                mid["body"] = handler.wfile.getvalue()
            if self.i >= len(self.parts):
                return b""
            part = self.parts[self.i]
            self.i += 1
            return part

    handler = _FakeHandler()
    handler._stream_sse_content_length = MethodType(
        proxy.ProxyHandler._stream_sse_content_length, handler
    )
    try:
        MethodType(proxy.ProxyHandler._stream_sse_content_length, handler)(_GatedUpstream())
    finally:
        proxy.SSE_STREAM_BYTES = old_cap
    header_map = dict(handler.headers)
    body = handler.wfile.getvalue()
    assert handler.status == 200
    assert header_map["Content-Type"] == "text/event-stream"
    assert header_map["Content-Length"] == str(cap)
    assert "Transfer-Encoding" not in header_map
    assert len(body) == cap
    assert body.startswith(first + rest)
    assert b"data: [DONE]" in body
    assert mid.get("status") == 200
    assert mid["headers"].get("Content-Length") == str(cap)
    assert "Transfer-Encoding" not in mid["headers"]
    assert mid["body"] == first


def test_write_blocked_sse_uses_content_length(proxy):
    from types import MethodType

    handler = _FakeHandler()
    handler._write_sse_bytes = MethodType(proxy.ProxyHandler._write_sse_bytes, handler)
    MethodType(proxy.ProxyHandler._write_blocked_sse, handler)(
        ALLOWED, proxy.parse_guardrails_outcome(ALLOWED)
    )
    header_map = dict(handler.headers)
    body = handler.wfile.getvalue()
    assert handler.status == 200
    assert header_map["Content-Length"] == str(len(body))
    assert "Transfer-Encoding" not in header_map
    assert b"data: [DONE]" in body


def test_add_overhead_seconds_is_cumulative(proxy):
    proxy.add_overhead_seconds(1.0)
    proxy.add_overhead_seconds(2.0)
    proxy.add_overhead_seconds(0.0)
    proxy.add_overhead_seconds(-1.0)
    text = proxy.metrics_text()
    assert "pca_guardrails_overhead_seconds_total 3.0" in text
    assert "# TYPE pca_guardrails_overhead_seconds_total counter" in text


def test_content_length_pad_records_overhead(proxy, monkeypatch):
    from types import MethodType

    recorded: list[float] = []
    monkeypatch.setattr(proxy, "add_overhead_seconds", recorded.append)
    first = b'data: {"choices":[{"delta":{"content":"p"}}]}\n\n'
    rest = b"data: [DONE]\n\n"
    cap = 256
    old_cap = proxy.SSE_STREAM_BYTES
    proxy.SSE_STREAM_BYTES = cap

    class _Upstream:
        def __init__(self) -> None:
            self.parts = [first, rest]
            self.i = 0

        def read(self, n: int = -1) -> bytes:
            if self.i >= len(self.parts):
                return b""
            part = self.parts[self.i]
            self.i += 1
            return part

    handler = _FakeHandler()
    handler._stream_sse_content_length = MethodType(
        proxy.ProxyHandler._stream_sse_content_length, handler
    )
    try:
        MethodType(proxy.ProxyHandler._stream_sse_content_length, handler)(_Upstream())
    finally:
        proxy.SSE_STREAM_BYTES = old_cap
    assert recorded
    assert all(delta >= 0 for delta in recorded)
    assert len(handler.wfile.getvalue()) == cap


def test_clip_sse_chunk_keeps_done_on_overflow(proxy):
    done = proxy.SSE_DONE
    assert proxy.clip_sse_chunk(b"abc", 0, 10) == b"abc"
    clipped = proxy.clip_sse_chunk(b"x" * 100, 0, 32)
    assert len(clipped) == 32
    assert clipped.endswith(done)


def test_stream_sse_uses_read1_not_read(proxy):
    from types import MethodType

    first = b'data: {"choices":[{"delta":{"content":"p"}}]}\n\n'
    rest = b"data: [DONE]\n\n"
    cap = 256
    old_cap = proxy.SSE_STREAM_BYTES
    proxy.SSE_STREAM_BYTES = cap

    class _Read1Only:
        def __init__(self) -> None:
            self.parts = [first, rest]

        def read(self, n: int = -1) -> bytes:
            raise AssertionError("read() waits for 4096 bytes")

        def read1(self, n: int = -1) -> bytes:
            if not self.parts:
                return b""
            return self.parts.pop(0)

    handler = _FakeHandler()
    handler._stream_sse_content_length = MethodType(
        proxy.ProxyHandler._stream_sse_content_length, handler
    )
    try:
        MethodType(proxy.ProxyHandler._stream_sse_content_length, handler)(_Read1Only())
    finally:
        proxy.SSE_STREAM_BYTES = old_cap
    body = handler.wfile.getvalue()
    assert len(body) == cap
    assert body.startswith(first + rest)
    assert b"data: [DONE]" in body


def test_stream_sse_overflow_still_has_done(proxy):
    from types import MethodType

    cap = 48
    old_cap = proxy.SSE_STREAM_BYTES
    proxy.SSE_STREAM_BYTES = cap
    payload = b"data: " + (b"t" * 80) + b"\n\n"

    class _Huge:
        def __init__(self) -> None:
            self.sent = False

        def read(self, n: int = -1) -> bytes:
            if self.sent:
                return b""
            self.sent = True
            return payload

    handler = _FakeHandler()
    handler._stream_sse_content_length = MethodType(
        proxy.ProxyHandler._stream_sse_content_length, handler
    )
    try:
        MethodType(proxy.ProxyHandler._stream_sse_content_length, handler)(_Huge())
    finally:
        proxy.SSE_STREAM_BYTES = old_cap
    body = handler.wfile.getvalue()
    assert len(body) == cap
    assert b"data: [DONE]" in body
