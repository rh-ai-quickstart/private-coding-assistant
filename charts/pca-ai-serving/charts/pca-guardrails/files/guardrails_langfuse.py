"""Langfuse ingest for flagged (block/warn) guardrails outcomes."""

from __future__ import annotations

import base64
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from guardrails_outcome import blocked_message, header

LANGFUSE_BASE_URL = os.environ.get(
    "LANGFUSE_BASE_URL",
    "http://pca-langfuse-web:3000",
).rstrip("/")

_EMIT_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pca-guardrails-lf")


def _langfuse_keys():
    return os.environ.get("LANGFUSE_PUBLIC_KEY") or "", os.environ.get(
        "LANGFUSE_SECRET_KEY"
    ) or ""


def _post_langfuse(payload):
    public_key, secret_key = _langfuse_keys()
    if not public_key or not secret_key:
        return
    auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
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
        print(f"[proxy] Langfuse emit failed: {err}", flush=True)


def _extract_input(payload):
    if isinstance(payload, dict):
        if "messages" in payload:
            return payload["messages"]
        if "prompt" in payload:
            return payload["prompt"]
    return payload


def langfuse_flagged_batch(request_payload, orch_body, outcome, headers):
    """Build a Langfuse ingestion batch for a flagged (block or warn) outcome."""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    trace_id = str(uuid.uuid4())
    gen_id = str(uuid.uuid4())
    user_id = header(headers, "X-PCA-User")
    devspace = header(headers, "X-PCA-DevSpace")
    team = header(headers, "X-PCA-Team")
    metadata = {
        "hits": [
            {
                "detector_id": h.detector_id,
                "detection_type": h.detection_type,
                "detection": h.detection,
                "text": h.text,
                "score": h.score,
                "direction": h.direction,
            }
            for h in outcome.hits
        ],
        "action": outcome.action,
    }
    if devspace:
        metadata["devspace"] = devspace
    if team:
        metadata["team"] = team
    tags = ["guardrails:flagged"]
    if outcome.action == "block":
        tags.append("guardrails:blocked")
    elif outcome.action == "warn":
        tags.append("guardrails:warned")
    if team:
        tags.append(f"team:{team}")
    if devspace:
        tags.append(f"devspace:{devspace}")
    if outcome.action == "block":
        output_data = blocked_message(outcome.hits)
    else:
        output_data = orch_body
    model = None
    if isinstance(request_payload, dict):
        model = request_payload.get("model")
    elif isinstance(orch_body, dict):
        model = orch_body.get("model")
    return {
        "batch": [
            {
                "id": str(uuid.uuid4()),
                "type": "trace-create",
                "timestamp": now,
                "body": {
                    "id": trace_id,
                    "name": "guardrails-flagged",
                    "userId": user_id,
                    "metadata": metadata,
                    "tags": tags,
                    "input": _extract_input(request_payload),
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
                    "name": "guardrails-flagged",
                    "model": model,
                    "input": _extract_input(request_payload),
                    "output": output_data,
                    "startTime": now,
                    "endTime": now,
                },
            },
        ]
    }


def schedule_flagged_langfuse(request_payload, orch_body, outcome, headers):
    public_key, secret_key = _langfuse_keys()
    if not public_key or not secret_key:
        return
    if not outcome.action:
        return
    payload = langfuse_flagged_batch(request_payload, orch_body, outcome, headers)
    _EMIT_POOL.submit(_post_langfuse, payload)
