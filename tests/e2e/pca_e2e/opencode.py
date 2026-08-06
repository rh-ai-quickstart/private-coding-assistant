"""HTTP client + in-pod helpers for the OpenCode Web server (port 4096)."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

import httpx

from pca_e2e import oc

log = logging.getLogger(__name__)

DEFAULT_USERNAME = "opencode"
MESSAGE_TIMEOUT_SECS = 300
DIRECTORY_HEADER = "x-opencode-directory"


def _event_session_id(payload: dict[str, Any]) -> str | None:
    """Best-effort session id from an OpenCode SSE event payload."""
    for key in ("sessionID", "sessionId", "session_id"):
        if payload.get(key):
            return str(payload[key])
    props = payload.get("properties") or payload.get("payload") or {}
    if isinstance(props, dict):
        for key in ("sessionID", "sessionId", "session_id"):
            if props.get(key):
                return str(props[key])
        info = props.get("info") or {}
        if isinstance(info, dict) and info.get("sessionID"):
            return str(info["sessionID"])
    info = payload.get("info") or {}
    if isinstance(info, dict) and info.get("sessionID"):
        return str(info["sessionID"])
    return None


def _event_is_generation_activity(payload: dict[str, Any]) -> bool:
    """True if this event indicates assistant text/tool activity started."""
    etype = str(payload.get("type") or payload.get("event") or "").lower()
    activity_hints = (
        "message.part",
        "part.updated",
        "part.delta",
        "text-delta",
        "text_delta",
        "tool",
        "reasoning",
        "assistant",
    )
    if any(h in etype for h in activity_hints):
        return True
    props = payload.get("properties") or payload.get("payload") or {}
    if not isinstance(props, dict):
        return False
    part = props.get("part") or props.get("delta") or {}
    if isinstance(part, dict):
        ptype = str(part.get("type") or "").lower()
        if ptype in {"text", "tool", "tool-invocation", "reasoning", "step-start"}:
            return True
        if part.get("text") or part.get("tool") or part.get("content"):
            return True
    return False


def _event_is_assistant_text(payload: dict[str, Any]) -> bool:
    """True if this event is assistant text (not tool/reasoning/step-start).

    Used for TTFT / prefill: first non-empty text token or text part.
    """
    etype = str(payload.get("type") or payload.get("event") or "").lower()
    if "text-delta" in etype or "text_delta" in etype:
        return True
    # Bare "text" event types, but not tool/reasoning disguised names.
    if etype in {"text", "message.text", "assistant.text"}:
        return True
    props = payload.get("properties") or payload.get("payload") or {}
    if not isinstance(props, dict):
        return False
    part = props.get("part") or props.get("delta") or {}
    if not isinstance(part, dict):
        return False
    ptype = str(part.get("type") or "").lower()
    if ptype in {"tool", "tool-invocation", "reasoning", "step-start"}:
        return False
    if ptype == "text":
        text = part.get("text") or part.get("content") or ""
        return bool(str(text).strip())
    # text-delta style parts without explicit type
    if part.get("text") and ptype in {"", "delta", "text-delta", "text_delta"}:
        return bool(str(part.get("text") or "").strip())
    return False


class OpenCodeError(RuntimeError):
    pass


def message_text(message_body: dict[str, Any]) -> str:
    parts = message_body.get("parts") or []
    chunks: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text" and part.get("text"):
            chunks.append(str(part["text"]))
    info = message_body.get("info") or {}
    if not chunks and isinstance(info, dict):
        for key in ("content", "text", "error"):
            if info.get(key):
                chunks.append(str(info[key]))
    return "\n".join(chunks).strip()


def _assistant_output_tokens(message: dict[str, Any]) -> int:
    """Return output tokens if this looks like an assistant/model completion.

    Returns 0 for non-assistant messages or when output tokens are missing/zero.
    """
    info = message.get("info") if isinstance(message.get("info"), dict) else {}
    role = str(
        info.get("role")
        or message.get("role")
        or info.get("type")
        or message.get("type")
        or ""
    ).lower()
    if role not in {"assistant", "model", "ai"}:
        return 0
    for blob in (
        info.get("tokens"),
        info.get("usage"),
        message.get("tokens"),
        message.get("usage"),
    ):
        if not isinstance(blob, dict):
            continue
        try:
            out = int(
                blob.get("output")
                or blob.get("completion_tokens")
                or blob.get("output_tokens")
                or 0
            )
        except (TypeError, ValueError):
            continue
        if out > 0:
            return out
    return 0


def resolve_model_ids(namespace: str, pod: str) -> tuple[str, str]:
    """Return (provider_id, model_id) from pod env / opencode.json."""
    result = oc.exec_in_pod(
        namespace,
        pod,
        "bash",
        "-lc",
        r"""
python3 - <<'PY'
import json, os
model = os.environ.get("VLLM_MODEL_ID") or os.environ.get("OPENAI_MODEL") or ""
path = os.path.expanduser("~/.config/opencode/opencode.json")
try:
    cfg = json.load(open(path, encoding="utf-8"))
    m = cfg.get("model") or ""
    if "/" in m:
        provider, mid = m.split("/", 1)
        print(provider)
        print(mid)
        raise SystemExit(0)
except Exception:
    pass
print("vllm")
print(model or "unknown")
PY
""",
        timeout=30,
    )
    lines = [ln.strip() for ln in (result.stdout or "").splitlines() if ln.strip()]
    if len(lines) < 2:
        raise OpenCodeError(f"cannot resolve model ids: {result.stdout!r}")
    return lines[0], lines[1]


class OpenCodeClient:
    def __init__(
        self,
        base_url: str,
        password: str,
        *,
        username: str = DEFAULT_USERNAME,
        directory: str | None = None,
        timeout_secs: float = MESSAGE_TIMEOUT_SECS,
    ):
        self.base_url = base_url.rstrip("/")
        self.directory = directory
        self.timeout_secs = timeout_secs
        self._username = username
        self._password = password
        headers = {DIRECTORY_HEADER: directory} if directory else None
        self._client = httpx.Client(
            base_url=self.base_url,
            auth=(username, password),
            verify=False,
            timeout=httpx.Timeout(timeout_secs, connect=30.0),
            headers=headers,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OpenCodeClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        resp = self._client.request(
            method,
            path,
            json=json_body,
            timeout=timeout or self.timeout_secs,
        )
        if resp.status_code >= 400:
            raise OpenCodeError(
                f"{method} {path} -> {resp.status_code}: {resp.text[:800]}"
            )
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return resp.text

    def health(self) -> dict[str, Any]:
        body = self._request("GET", "/global/health", timeout=30.0)
        if not isinstance(body, dict):
            raise OpenCodeError(f"unexpected health response: {body!r}")
        if body.get("healthy") is not True:
            raise OpenCodeError(f"OpenCode unhealthy: {body!r}")
        return body

    def create_session(self, title: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if title:
            payload["title"] = title
        body = self._request("POST", "/session", json_body=payload or None)
        if not isinstance(body, dict) or not body.get("id"):
            raise OpenCodeError(f"create session failed: {body!r}")
        return body

    def send_message(
        self,
        session_id: str,
        text: str,
        *,
        provider_id: str | None = None,
        model_id: str | None = None,
        allow_permissions: bool = True,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"parts": [{"type": "text", "text": text}]}
        if provider_id and model_id:
            payload["model"] = {"providerID": provider_id, "modelID": model_id}

        wait = timeout or self.timeout_secs
        deadline = time.time() + wait
        last_error: Exception | None = None
        while time.time() < deadline:
            if allow_permissions:
                self.approve_pending_permissions(session_id)
            try:
                body = self._request(
                    "POST",
                    f"/session/{session_id}/message",
                    json_body=payload,
                    timeout=wait,
                )
                if allow_permissions:
                    self.approve_pending_permissions(session_id)
                if not isinstance(body, dict):
                    raise OpenCodeError(f"unexpected message response: {body!r}")
                err = (body.get("info") or {}).get("error")
                if err:
                    raise OpenCodeError(f"OpenCode assistant error: {err!r}")
                return body
            except OpenCodeError as exc:
                last_error = exc
                if allow_permissions and self.approve_pending_permissions(session_id):
                    time.sleep(1)
                    continue
                raise
        raise OpenCodeError(f"send_message timed out: {last_error}")

    def session_diff(self, session_id: str) -> Any:
        return self._request("GET", f"/session/{session_id}/diff", timeout=60.0)

    def list_session_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Return session messages (best-effort across OpenCode response shapes)."""
        body = self._request(
            "GET", f"/session/{session_id}/message", timeout=60.0
        )
        if isinstance(body, list):
            return [m for m in body if isinstance(m, dict)]
        if isinstance(body, dict):
            for key in ("data", "messages", "items"):
                items = body.get(key)
                if isinstance(items, list):
                    return [m for m in items if isinstance(m, dict)]
        return []

    def count_llm_calls(self, session_id: str) -> tuple[int, int]:
        """Count assistant/model steps with output tokens > 0.

        Returns (llm_calls, sum_output_tokens) for those steps.
        """
        calls = 0
        output_tokens = 0
        for msg in self.list_session_messages(session_id):
            out = _assistant_output_tokens(msg)
            if out > 0:
                calls += 1
                output_tokens += out
        return calls, output_tokens

    def run_turn_with_generation_timing(
        self,
        session_id: str,
        text: str,
        *,
        provider_id: str | None = None,
        model_id: str | None = None,
        timeout: float | None = None,
    ) -> tuple[dict[str, Any], float, float, float, float, float]:
        """Send a turn; return timing tuple for the OpenCode ladder.

        Returns:
            (response, generation_secs, gen_start, gen_end, prefill_secs, decode_secs)

        - generation_secs: first SSE activity (text/tool) → send_message returns
        - prefill_secs: prompt send → first assistant text token (TTFT)
        - decode_secs: first assistant text → turn end (may include later tools)
        """
        wait = timeout or self.timeout_secs
        gen_start_box: list[float] = []
        first_text_box: list[float] = []
        stop = threading.Event()
        sse_ready = threading.Event()
        headers = {DIRECTORY_HEADER: self.directory} if self.directory else None

        def _sse_reader() -> None:
            # Separate client: httpx.Client is not safe for concurrent use.
            try:
                with httpx.Client(
                    base_url=self.base_url,
                    auth=(self._username, self._password),
                    verify=False,
                    timeout=httpx.Timeout(wait + 60.0, connect=30.0),
                    headers=headers,
                ) as sse_client:
                    with sse_client.stream("GET", "/event") as resp:
                        if resp.status_code >= 400:
                            log.warning(
                                "OpenCode /event -> %s: %s",
                                resp.status_code,
                                resp.read()[:200],
                            )
                            return
                        sse_ready.set()
                        for line in resp.iter_lines():
                            if stop.is_set():
                                break
                            if not line or not line.startswith("data:"):
                                continue
                            raw = line.split(":", 1)[1].strip()
                            if not raw or raw == "[DONE]":
                                continue
                            try:
                                payload = json.loads(raw)
                            except json.JSONDecodeError:
                                continue
                            if not isinstance(payload, dict):
                                continue
                            sid = _event_session_id(payload)
                            if sid and sid != session_id:
                                continue
                            if sid is None and not _event_is_generation_activity(
                                payload
                            ):
                                continue
                            now = time.perf_counter()
                            if _event_is_generation_activity(payload) or (
                                sid == session_id
                                and str(payload.get("type") or "").startswith(
                                    "message"
                                )
                            ):
                                if not gen_start_box:
                                    gen_start_box.append(now)
                            if _event_is_assistant_text(payload) and not first_text_box:
                                first_text_box.append(now)
            except Exception as exc:  # noqa: BLE001 — timing aid only
                log.warning("OpenCode /event reader stopped: %s", exc)

        reader = threading.Thread(target=_sse_reader, name="opencode-sse", daemon=True)
        reader.start()
        try:
            if not sse_ready.wait(timeout=30.0):
                raise OpenCodeError(
                    f"OpenCode /event SSE not ready within 30s for session {session_id}"
                )
            prompt_send = time.perf_counter()
            resp = self.send_message(
                session_id,
                text,
                provider_id=provider_id,
                model_id=model_id,
                timeout=wait,
            )
            gen_end = time.perf_counter()
            if not gen_start_box:
                raise OpenCodeError(
                    "no OpenCode SSE generation frame observed for session "
                    f"{session_id} (cannot measure generation_secs)"
                )
            if not first_text_box:
                raise OpenCodeError(
                    "no OpenCode SSE assistant text frame observed for session "
                    f"{session_id} (cannot measure prefill_secs / decode_secs)"
                )
            gen_start = gen_start_box[0]
            first_text = first_text_box[0]
            generation_secs = max(gen_end - gen_start, 1e-6)
            prefill_secs = max(first_text - prompt_send, 1e-6)
            decode_secs = max(gen_end - first_text, 1e-6)
            return (
                resp,
                generation_secs,
                gen_start,
                gen_end,
                prefill_secs,
                decode_secs,
            )
        finally:
            stop.set()
            reader.join(timeout=2.0)

    def approve_pending_permissions(self, session_id: str) -> bool:
        approved = False
        try:
            status = self._request("GET", "/session/status", timeout=30.0)
        except OpenCodeError:
            status = None
        if isinstance(status, dict):
            entry = status.get(session_id) or {}
            pending = entry.get("permissions") or entry.get("permission") or []
            if isinstance(pending, dict):
                pending = [pending]
            for perm in pending:
                if not isinstance(perm, dict):
                    continue
                pid = perm.get("id") or perm.get("permissionID")
                if not pid:
                    continue
                try:
                    self._request(
                        "POST",
                        f"/session/{session_id}/permissions/{pid}",
                        json_body={"response": "once"},
                        timeout=30.0,
                    )
                    approved = True
                    log.info("approved OpenCode permission %s", pid)
                except OpenCodeError as exc:
                    log.warning("permission approve failed for %s: %s", pid, exc)
        return approved
