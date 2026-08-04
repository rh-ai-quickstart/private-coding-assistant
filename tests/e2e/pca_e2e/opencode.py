"""HTTP client + in-pod helpers for the OpenCode Web server (port 4096)."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from pca_e2e import oc

log = logging.getLogger(__name__)

DEFAULT_USERNAME = "opencode"
MESSAGE_TIMEOUT_SECS = 300
DIRECTORY_HEADER = "x-opencode-directory"


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
