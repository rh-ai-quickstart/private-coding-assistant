"""Direct gateway inter-token latency test.

Bypasses OpenCode and calls the MaaS gateway SSE endpoint directly, recording
the arrival time of every text-delta chunk. This lets us measure per-token
inter-arrival intervals independently of OpenCode's event batching.

Key question: does the guardrails proxy add per-token latency (reducing tok/s)
or only per-request latency (increasing TTFT, no effect on tok/s)?

If inter-token intervals are the same with/without guardrails → only TTFT is
affected (colleague's hypothesis is correct).

Usage:
  # With guardrails enabled:
  pytest tests/e2e/performance/test_inter_token_latency.py -v -s

  # After toggling guardrails off, run again and compare the printed output.

Credentials are read from dev-user1's DevWorkspace env (OPENAI_BASE_URL,
OPENAI_API_KEY) — same source OpenCode uses.
"""

from __future__ import annotations

import json
import random
import statistics
import time

import httpx
import pytest

from pca_e2e import oc
from pca_perf.config import user_namespace

MAX_TOKENS = 200
RUNS = 5


def _get_gateway_creds(ns: str) -> tuple[str, str, str]:
    """Return (base_url, api_key, model_id) from dev-user1's DevWorkspace spec."""
    dw = oc.find_opencode_devworkspace(ns)
    if dw is None:
        pytest.skip(f"No OpenCode DevWorkspace found in {ns}")
    env = oc.devworkspace_env(dw)
    base_url = env.get("OPENAI_BASE_URL", "").rstrip("/")
    model_id = env.get("VLLM_MODEL_ID") or env.get("OPENAI_MODEL", "")
    api_key = oc.secret_data("pca-maas-apikey", "api_key", ns).strip()
    if not base_url or not api_key or not model_id:
        pytest.skip(f"Gateway creds or model_id missing in {ns}")
    # OPENAI_BASE_URL already ends with /v1; build full endpoint
    endpoint = base_url.rstrip("/") + "/chat/completions"
    return endpoint, api_key, model_id


def _run_once(endpoint: str, api_key: str, model_id: str) -> dict:
    """Stream one completion and return timing breakdown."""
    seed = random.randint(100_000, 999_999)
    body = {
        "model": model_id,
        "messages": [
            {
                "role": "user",
                "content": (
                    f"[run-id:{seed}] Write a Python function called `add` that "
                    "takes two numbers and returns their sum. Include a docstring. "
                    "Do not add any other explanation."
                ),
            }
        ],
        "max_tokens": MAX_TOKENS,
        "stream": True,
        "stream_options": {"include_usage": True},
        "temperature": 0,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    chunk_times: list[float] = []
    t_send = time.perf_counter()
    completion_tokens = 0

    with httpx.stream(
        "POST",
        endpoint,
        json=body,
        headers=headers,
        timeout=120,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            try:
                chunk = json.loads(raw)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices") or []
            if choices:
                delta = (choices[0].get("delta") or {})
                if delta.get("content"):
                    chunk_times.append(time.perf_counter())
            usage = chunk.get("usage") or {}
            if usage.get("completion_tokens"):
                completion_tokens = int(usage["completion_tokens"])

    if len(chunk_times) < 2:
        return {}

    ttft_ms = (chunk_times[0] - t_send) * 1000
    intervals_ms = [
        (chunk_times[i + 1] - chunk_times[i]) * 1000
        for i in range(len(chunk_times) - 1)
    ]
    total_stream_secs = chunk_times[-1] - chunk_times[0]
    tok_s = len(chunk_times) / total_stream_secs if total_stream_secs > 0 else 0

    return {
        "seed": seed,
        "chunks": len(chunk_times),
        "completion_tokens": completion_tokens,
        "ttft_ms": ttft_ms,
        "avg_interval_ms": statistics.mean(intervals_ms),
        "p50_interval_ms": statistics.median(intervals_ms),
        "p95_interval_ms": statistics.quantiles(intervals_ms, n=20)[-1] if len(intervals_ms) >= 20 else max(intervals_ms),
        "tok_s": tok_s,
    }


def _print_run(i: int, r: dict) -> None:
    print(
        f"  run {i:2d}  seed={r['seed']}  chunks={r['chunks']:3d}  "
        f"TTFT={r['ttft_ms']:6.0f}ms  "
        f"avg_interval={r['avg_interval_ms']:5.1f}ms  "
        f"p50={r['p50_interval_ms']:5.1f}ms  "
        f"tok/s={r['tok_s']:5.1f}"
    )


def _print_summary(label: str, results: list[dict]) -> None:
    if not results:
        return
    print(f"\n{'='*70}")
    print(f"  {label}  ({len(results)} runs)")
    print(f"{'='*70}")
    for key, unit in [
        ("ttft_ms", "ms"),
        ("avg_interval_ms", "ms"),
        ("p50_interval_ms", "ms"),
        ("tok_s", "tok/s"),
    ]:
        vals = [r[key] for r in results]
        mean = statistics.mean(vals)
        stdev = statistics.stdev(vals) if len(vals) > 1 else 0.0
        print(f"  {key:22s}: mean={mean:7.2f}{unit}  stdev={stdev:6.2f}{unit}")


@pytest.mark.performance
def test_inter_token_latency(oc_user: str) -> None:  # noqa: ARG001
    ns = user_namespace(1)
    endpoint, api_key, model_id = _get_gateway_creds(ns)
    print(f"\nEndpoint: {endpoint}")
    print(f"Model:    {model_id}  max_tokens={MAX_TOKENS}  runs={RUNS}\n")

    results: list[dict] = []
    for i in range(1, RUNS + 1):
        r = _run_once(endpoint, api_key, model_id)
        if r:
            _print_run(i, r)
            results.append(r)
        time.sleep(1)

    _print_summary("RESULTS", results)
    assert results, "No successful runs"
