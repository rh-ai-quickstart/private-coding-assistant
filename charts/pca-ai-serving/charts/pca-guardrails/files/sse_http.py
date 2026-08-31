"""HTTP/1.1 chunked POST body + Content-Length SSE framing for Envoy.

Guardrails-only. Lock: tests/unit/test_shared_helper_copies.py.
"""

from __future__ import annotations

import time

# Envoy HTTP/1.1 chunked SSE is truncated (IncompleteRead). Content-Length
# is the framing that arrives complete. Declare this size up front, stream
# tokens, then pad with SSE comments so OpenCode sees a finished body.
# ~260B/token of vLLM SSE. N=4 OpenCode ladder is ~800 tokens (~200KiB);
# two LLM calls plus tool payloads need headroom. Clip still writes
# data: [DONE] so clients do not hang.
SSE_STREAM_BYTES = 512 * 1024
SSE_DONE = b"data: [DONE]\n\n"


def sse_content_length_pad(remain: int) -> bytes:
    """Exactly `remain` bytes of one SSE comment (not thousands of frames)."""
    if remain <= 0:
        return b""
    if remain == 1:
        return b":"
    if remain == 2:
        return b":\n"
    return b":" + (b" " * (remain - 3)) + b"\n\n"


def read_upstream_sse_chunk(body, size: int = 4096) -> bytes:
    """Prefer read1 so TTFB is the first token, not a 4KiB socket fill."""
    read1 = getattr(body, "read1", None)
    if read1 is not None:
        return read1(size)
    return body.read(size)


def clip_sse_chunk(chunk: bytes, n: int, cap: int) -> bytes:
    """Fit chunk into cap-n bytes. On overflow, keep a terminating data: [DONE]."""
    room = cap - n
    if room <= 0 or not chunk:
        return b""
    if len(chunk) <= room:
        return chunk
    if room <= len(SSE_DONE):
        return SSE_DONE[:room]
    return chunk[: room - len(SSE_DONE)] + SSE_DONE


def stream_sse_content_length(
    handler,
    body,
    *,
    cap: int = SSE_STREAM_BYTES,
    extra_headers: dict | None = None,
    on_pad=None,
) -> None:
    """Send Content-Length first, then upstream SSE, then comment padding.

    Envoy re-chunks identity/chunked HTTP/1.1 and drops the tail
    (IncompleteRead, OpenCode hang). Declared Content-Length is the
    framing that already arrives complete. Headers go out before the
    GPU finishes so TTFB is first token, not full generation.
    """
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Content-Length", str(cap))
    handler.send_header("Connection", "close")
    for key, value in (extra_headers or {}).items():
        handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.flush()
    n = 0

    def _write(data: bytes, flush: bool = True) -> None:
        nonlocal n
        data = clip_sse_chunk(data, n, cap)
        if not data:
            return
        handler.wfile.write(data)
        if flush:
            handler.wfile.flush()
        n += len(data)

    try:
        while n < cap:
            chunk = read_upstream_sse_chunk(body)
            if not chunk:
                break
            _write(chunk)
        remain = cap - n
        if remain:
            # One write: flushing 4KiB pad chunks costs ~Envoy RTT each.
            t0 = time.monotonic()
            _write(sse_content_length_pad(remain), flush=True)
            if on_pad is not None:
                on_pad(time.monotonic() - t0)
    except BrokenPipeError:
        return


def read_request_body(headers, rfile) -> bytes:
    """Read POST body from Content-Length or chunked Transfer-Encoding.

    Envoy (MaaS Gateway) often forwards POST as chunked HTTP/1.1 without
    Content-Length. BaseHTTPRequestHandler does not decode that itself.
    """
    te = (headers.get("Transfer-Encoding") or "").lower()
    if "chunked" in te:
        chunks: list[bytes] = []
        while True:
            size_line = rfile.readline()
            if not size_line:
                break
            size = int(size_line.split(b";", 1)[0].strip(), 16)
            if size == 0:
                while True:
                    trailer = rfile.readline()
                    if not trailer or trailer in (b"\r\n", b"\n"):
                        break
                break
            chunks.append(rfile.read(size))
            rfile.read(2)
        return b"".join(chunks)
    length = int(headers.get("Content-Length") or 0)
    return rfile.read(length) if length else b""
