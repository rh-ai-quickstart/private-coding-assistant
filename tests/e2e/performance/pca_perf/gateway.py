"""Concurrent chat/completions load through pca-ai-gateway (generation-timed)."""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx

from pca_perf.config import (
    GATEWAY_PROMPT,
    ai_gateway_service_name,
    gateway_chat_timeout_secs,
    gateway_max_tokens,
)
from pca_perf.forward import PortForward
from pca_perf.gpu import GpuSampler
from pca_perf.metrics import WorkerResult, stage_from_workers, usage_token_parts

log = logging.getLogger(__name__)


def _chunk_has_content(chunk: dict[str, Any]) -> bool:
    for choice in chunk.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        delta = choice.get("delta") or {}
        if not isinstance(delta, dict):
            continue
        if delta.get("content") or delta.get("reasoning") or delta.get("tool_calls"):
            return True
        msg = choice.get("message") or {}
        if isinstance(msg, dict) and (msg.get("content") or msg.get("reasoning")):
            return True
    return False


def _one_chat(
    base_url: str,
    api_key: str,
    model_id: str,
    max_tokens: int,
    timeout: float,
) -> WorkerResult:
    # One client per worker — httpx.Client is not safe for concurrent use.
    try:
        with httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            verify=False,
            timeout=httpx.Timeout(timeout, connect=30.0),
        ) as client:
            gen_start: float | None = None
            prompt_tokens = 0
            completion_tokens = 0
            tokens = 0
            saw_content = False
            t_send = time.perf_counter()
            with client.stream(
                "POST",
                "/v1/chat/completions",
                json={
                    "model": model_id,
                    "messages": [{"role": "user", "content": GATEWAY_PROMPT}],
                    "stream": True,
                    "stream_options": {"include_usage": True},
                    "max_tokens": max_tokens,
                    "chat_template_kwargs": {"enable_thinking": False},
                },
            ) as resp:
                if resp.status_code >= 400:
                    body = resp.read().decode("utf-8", errors="replace")[:200]
                    return WorkerResult(
                        ok=False, error=f"HTTP {resp.status_code}: {body}"
                    )
                for line in resp.iter_lines():
                    if not line:
                        continue
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(chunk, dict):
                        continue
                    if _chunk_has_content(chunk):
                        if gen_start is None:
                            gen_start = time.perf_counter()
                        saw_content = True
                    usage = chunk.get("usage")
                    if isinstance(usage, dict):
                        p, c, total = usage_token_parts({"usage": usage})
                        if p or c or total:
                            prompt_tokens = p or prompt_tokens
                            completion_tokens = c or completion_tokens
                            tokens = total or tokens
            gen_end = time.perf_counter()
            if not saw_content or gen_start is None:
                return WorkerResult(
                    ok=False,
                    error="stream finished with no content chunks (no generation window)",
                )
            generation_secs = max(gen_end - gen_start, 1e-6)
            ttft_secs = max(gen_start - t_send, 0.0)
            return WorkerResult(
                ok=True,
                tokens=tokens,
                generation_secs=generation_secs,
                gen_start=gen_start,
                gen_end=gen_end,
                ttft_secs=ttft_secs,
                prompt_tokens=prompt_tokens or None,
                completion_tokens=completion_tokens or None,
            )
    except Exception as exc:  # noqa: BLE001 — aggregate into stage result
        return WorkerResult(ok=False, error=str(exc))


def run_gateway_stage(
    *,
    ai_namespace: str,
    api_key: str,
    model_id: str,
    n: int,
):
    timeout = gateway_chat_timeout_secs()
    max_tokens = gateway_max_tokens()
    svc = ai_gateway_service_name()

    with PortForward(
        ai_namespace, f"svc/{svc}", 443, scheme="https"
    ) as pf:
        try:
            with httpx.Client(
                base_url=pf.base_url,
                headers={"Authorization": f"Bearer {api_key}"},
                verify=False,
                timeout=httpx.Timeout(30.0, connect=30.0),
            ) as probe:
                probe.get("/v1/models")
        except Exception as exc:  # noqa: BLE001
            log.warning("GET /v1/models failed (continuing): %s", exc)

        workers: list[WorkerResult] = []
        with GpuSampler(ai_namespace) as sampler:
            with ThreadPoolExecutor(max_workers=n) as pool:
                futures = [
                    pool.submit(
                        _one_chat, pf.base_url, api_key, model_id, max_tokens, timeout
                    )
                    for _ in range(n)
                ]
                for fut in as_completed(futures):
                    workers.append(fut.result())
            peak_gpu = sampler.peak_util_pct

    return stage_from_workers("gateway", n, workers, gpu_util_pct=peak_gpu)
