#!/usr/bin/env python3
"""Talk to OpenCode Web (port-forwarded) the same way tests/e2e does.

Env (password must not be argv or evidence):
  OPENCODE_URL       http://127.0.0.1:<port>
  OPENCODE_PASSWORD  Basic Auth password (user defaults to opencode)
  OPENCODE_USER      default opencode
  PROMPT             user text
  EVIDENCE_DIR       write request/response JSON here
  RUN_ID             session title token
  EXPECT             clean (default) or block
  PROVIDER_ID        optional
  MODEL_ID           optional
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

DEFAULT_USER = "opencode"
BLOCK_MARKERS = (
    "guardrails blocked",
    "credential",
    "secret",
    "akia",
    "unsuitable_input",
)


def _die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def _is_block(text: str) -> bool:
    lower = text.lower()
    return any(m in lower for m in BLOCK_MARKERS)


def _message_text(body: dict[str, Any]) -> str:
    chunks: list[str] = []
    for part in body.get("parts") or []:
        if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
            chunks.append(str(part["text"]))
    info = body.get("info") or {}
    if not chunks and isinstance(info, dict):
        for key in ("content", "text", "error"):
            if info.get(key):
                chunks.append(str(info[key]))
    return "\n".join(chunks).strip()


class OpenCodeClient:
    def __init__(self, base: str, user: str, password: str, timeout: float) -> None:
        import base64

        self.base = base.rstrip("/")
        self._auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        self.timeout = timeout

    def request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> Any:
        data = None
        headers = {"Authorization": self._auth, "Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            self.base + path, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                status = getattr(resp, "status", 200)
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", "replace")[:800]
            raise RuntimeError(f"{method} {path} -> {exc.code}: {err_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"{method} {path} failed: {exc}") from exc
        if not raw:
            return {"_status": status}
        try:
            parsed = json.loads(raw.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            return {"_status": status, "_text": raw.decode("utf-8", "replace")}
        if isinstance(parsed, dict):
            parsed.setdefault("_status", status)
        return parsed


def main() -> None:
    url = os.environ.get("OPENCODE_URL", "").strip()
    password = os.environ.get("OPENCODE_PASSWORD", "")
    user = os.environ.get("OPENCODE_USER", DEFAULT_USER)
    prompt = os.environ.get("PROMPT", "").strip()
    evidence = os.environ.get("EVIDENCE_DIR", "").strip()
    run_id = os.environ.get("RUN_ID", "verify")
    expect = os.environ.get("EXPECT", "clean").strip().lower()
    provider = os.environ.get("PROVIDER_ID", "").strip()
    model = os.environ.get("MODEL_ID", "").strip()
    timeout = float(os.environ.get("OPENCODE_TIMEOUT", "300"))

    if not url:
        _die("OPENCODE_URL is empty")
    if not password:
        _die("OPENCODE_PASSWORD is empty")
    if not prompt:
        _die("PROMPT is empty")
    if not evidence:
        _die("EVIDENCE_DIR is empty")
    if expect not in {"clean", "block"}:
        _die("EXPECT must be clean or block")

    os.makedirs(evidence, exist_ok=True)
    req_path = os.path.join(evidence, "opencode-chat-request.json")
    resp_path = os.path.join(evidence, "opencode-chat-response.json")
    request_doc = {
        "prompt": prompt,
        "expect": expect,
        "run_id": run_id,
        "url_host": url,
    }
    json.dump(request_doc, open(req_path, "w"), indent=2)
    json.dump(request_doc, open(os.path.join(evidence, "chat-request.json"), "w"), indent=2)

    client = OpenCodeClient(url, user, password, timeout)
    health = client.request("GET", "/global/health")
    if not isinstance(health, dict) or health.get("healthy") is not True:
        _die(f"OpenCode unhealthy: {health!r}")

    session = client.request("POST", "/session", {"title": f"pca-verify-{run_id}"})
    if not isinstance(session, dict) or not session.get("id"):
        _die(f"create session failed: {session!r}")
    sid = str(session["id"])

    payload: dict[str, Any] = {"parts": [{"type": "text", "text": prompt}]}
    if provider and model:
        payload["model"] = {"providerID": provider, "modelID": model}

    assistant = ""
    raw_resp: Any
    try:
        raw_resp = client.request("POST", f"/session/{sid}/message", payload)
        if isinstance(raw_resp, dict):
            err = (raw_resp.get("info") or {}).get("error")
            if err:
                assistant = str(err)
            else:
                assistant = _message_text(raw_resp)
        else:
            assistant = str(raw_resp)
    except RuntimeError as exc:
        raw_resp = {"error": str(exc)}
        assistant = str(exc)

    json.dump(raw_resp, open(resp_path, "w"), indent=2, default=str)
    json.dump(raw_resp, open(os.path.join(evidence, "chat-response.json"), "w"), indent=2, default=str)

    blocked = _is_block(assistant)
    print(f"STATUS=200")
    print(f"SESSION_ID={sid}")
    print(f"BLOCKED={'true' if blocked else 'false'}")
    print("ASSISTANT=" + assistant.replace("\n", " ")[:500])
    print(f"BODY_PATH={resp_path}")

    if expect == "block":
        if not blocked:
            _die(f"expected guardrails block, got assistant={assistant[:400]!r}")
        return
    if blocked:
        _die(f"clean chat was blocked by guardrails: {assistant[:400]!r}")
    if not assistant.strip():
        _die("empty OpenCode assistant text")


if __name__ == "__main__":
    main()
