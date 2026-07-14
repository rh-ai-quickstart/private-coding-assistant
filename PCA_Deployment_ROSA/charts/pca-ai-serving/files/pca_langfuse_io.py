"""vLLM OpenAI-server middleware: store full prompt/completion in Langfuse after each response.

Loaded via: --middleware pca_langfuse_io.langfuse_io_middleware

Does not block TTFT: streams through to the client, then fire-and-forget POSTs to Langfuse.
Failures only log; they never fail the client request.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger("pca_langfuse_io")

LANGFUSE_BASE_URL = os.environ.get(
    "LANGFUSE_BASE_URL",
    "http://pca-langfuse-web:3000",
).rstrip("/")
LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY", "")
ENABLED = os.environ.get("PCA_LANGFUSE_IO_CAPTURE", "full").lower() == "full"

_CAPTURE_SUFFIXES = ("/v1/chat/completions", "/v1/completions", "/chat/completions", "/completions")


def _enabled() -> bool:
    return ENABLED and bool(LANGFUSE_PUBLIC_KEY) and bool(LANGFUSE_SECRET_KEY)


def _header(headers: Any, name: str) -> str | None:
    """Read a header case-insensitively from a Starlette/ASGI Headers object or mapping."""
    if headers is None:
        return None
    lower = name.lower()
    try:
        for key, value in headers.items():
            if str(key).lower() == lower and value:
                return str(value)
    except Exception:
        pass
    getter = getattr(headers, "get", None)
    if callable(getter):
        value = getter(name) or getter(lower)
        if value:
            return str(value)
    return None


def _extract_input(payload: dict[str, Any]) -> Any:
    if "messages" in payload:
        return payload["messages"]
    if "prompt" in payload:
        return payload["prompt"]
    return payload


def _extract_output(body_bytes: bytes, content_type: str | None) -> Any:
    text = body_bytes.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    ct = (content_type or "").lower()
    if "text/event-stream" in ct or text.startswith("data:"):
        contents: list[str] = []
        for line in text.splitlines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            for choice in chunk.get("choices") or []:
                delta = choice.get("delta") or {}
                if delta.get("content"):
                    contents.append(str(delta["content"]))
                msg = choice.get("message") or {}
                if msg.get("content"):
                    contents.append(str(msg["content"]))
                if choice.get("text"):
                    contents.append(str(choice["text"]))
        return "".join(contents) if contents else text
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text
    choices = parsed.get("choices") or []
    if not choices:
        return parsed
    parts: list[str] = []
    for choice in choices:
        msg = choice.get("message") or {}
        if msg.get("content"):
            parts.append(str(msg["content"]))
        if choice.get("text"):
            parts.append(str(choice["text"]))
    return "\n".join(parts) if parts else parsed


def _map_usage(usage: dict[str, Any]) -> dict[str, Any] | None:
    """Map OpenAI-style usage fields to Langfuse generation usage keys."""
    out: dict[str, Any] = {}
    if "prompt_tokens" in usage:
        out["input"] = usage["prompt_tokens"]
    if "completion_tokens" in usage:
        out["output"] = usage["completion_tokens"]
    if "total_tokens" in usage:
        out["total"] = usage["total_tokens"]
    return out or None


def _usage_from_response(body_bytes: bytes) -> dict[str, Any] | None:
    text = body_bytes.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    if text.startswith("data:") or "\ndata:" in text:
        last: dict[str, Any] | None = None
        for line in text.splitlines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            if not isinstance(chunk, dict):
                continue
            usage = chunk.get("usage")
            if isinstance(usage, dict):
                mapped = _map_usage(usage)
                if mapped:
                    last = mapped
        return last
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    usage = parsed.get("usage")
    if not isinstance(usage, dict):
        return None
    return _map_usage(usage)


def _post_langfuse(payload: dict[str, Any]) -> None:
    auth = base64.b64encode(
        f"{LANGFUSE_PUBLIC_KEY}:{LANGFUSE_SECRET_KEY}".encode()
    ).decode()
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
        logger.warning(f"Langfuse I/O emit failed: {err}")


def _emit_async(
    *,
    input_data: Any,
    output_data: Any,
    model: str | None,
    user_id: str | None,
    devspace: str | None,
    team: str | None,
    usage: dict[str, Any] | None,
) -> None:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    trace_id = str(uuid.uuid4())
    gen_id = str(uuid.uuid4())
    metadata: dict[str, Any] = {}
    if devspace:
        metadata["devspace"] = devspace
    if team:
        metadata["team"] = team
    tags: list[str] = []
    if team:
        tags.append(f"team:{team}")
    if devspace:
        tags.append(f"devspace:{devspace}")

    batch = [
        {
            "id": str(uuid.uuid4()),
            "type": "trace-create",
            "timestamp": now,
            "body": {
                "id": trace_id,
                "name": "vllm-chat",
                "userId": user_id,
                "metadata": metadata or None,
                "tags": tags or None,
                "input": input_data,
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
                "name": "chat-completion",
                "model": model,
                "input": input_data,
                "output": output_data,
                "usage": usage,
                "startTime": now,
                "endTime": now,
            },
        },
    ]
    threading.Thread(
        target=_post_langfuse,
        args=({"batch": batch},),
        name="pca-langfuse-io",
        daemon=True,
    ).start()


async def langfuse_io_middleware(request, call_next):
    """Starlette HTTP middleware entrypoint for vLLM `--middleware`."""
    path = request.url.path
    if not _enabled() or not any(path.endswith(s) for s in _CAPTURE_SUFFIXES):
        return await call_next(request)

    try:
        body = await request.body()
    except Exception:
        return await call_next(request)

    user_id = _header(request.headers, "X-PCA-User")
    devspace = _header(request.headers, "X-PCA-DevSpace")
    team = _header(request.headers, "X-PCA-Team")
    model = None
    input_data: Any = None
    try:
        payload = json.loads(body.decode("utf-8") or "{}")
        if isinstance(payload, dict):
            input_data = _extract_input(payload)
            model = payload.get("model")
            # vLLM only emits a final SSE usage chunk when include_usage is set.
            if payload.get("stream"):
                opts = payload.get("stream_options")
                if not isinstance(opts, dict):
                    opts = {}
                opts["include_usage"] = True
                payload["stream_options"] = opts
                body = json.dumps(payload).encode("utf-8")
    except (json.JSONDecodeError, UnicodeDecodeError):
        input_data = body.decode("utf-8", errors="replace")

    # Re-inject body so the downstream app can still read it (possibly rewritten).
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request = request.__class__(request.scope, receive)

    response = await call_next(request)

    response_headers = getattr(response, "headers", None)
    content_type = _header(response_headers, "content-type")
    status_code = getattr(response, "status_code", 200)

    body_iterator = getattr(response, "body_iterator", None)
    if body_iterator is not None:

        async def tee():
            chunks: list[bytes] = []
            try:
                async for chunk in body_iterator:
                    if isinstance(chunk, memoryview):
                        chunk = chunk.tobytes()
                    elif isinstance(chunk, bytearray):
                        chunk = bytes(chunk)
                    elif not isinstance(chunk, bytes):
                        chunk = bytes(chunk)
                    chunks.append(chunk)
                    yield chunk
            finally:
                if status_code < 400 and input_data is not None:
                    full = b"".join(chunks)
                    try:
                        _emit_async(
                            input_data=input_data,
                            output_data=_extract_output(full, content_type),
                            model=model,
                            user_id=user_id,
                            devspace=devspace,
                            team=team,
                            usage=_usage_from_response(full),
                        )
                    except Exception as err:
                        logger.warning(f"Langfuse I/O schedule failed: {err}")

        from starlette.responses import StreamingResponse

        return StreamingResponse(
            tee(),
            status_code=status_code,
            headers=dict(response_headers) if response_headers is not None else None,
            media_type=getattr(response, "media_type", None),
            background=getattr(response, "background", None),
        )

    # Non-streaming response with .body attribute
    try:
        resp_body = getattr(response, "body", b"") or b""
        if isinstance(resp_body, memoryview):
            resp_body = resp_body.tobytes()
        elif not isinstance(resp_body, bytes):
            resp_body = bytes(resp_body)
        if status_code < 400 and input_data is not None:
            _emit_async(
                input_data=input_data,
                output_data=_extract_output(resp_body, content_type),
                model=model,
                user_id=user_id,
                devspace=devspace,
                team=team,
                usage=_usage_from_response(resp_body),
            )
    except Exception as err:
        logger.warning(f"Langfuse I/O capture failed: {err}")

    return response
