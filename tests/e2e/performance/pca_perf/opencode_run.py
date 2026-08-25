"""Concurrent OpenCode agent load (generation-timed; metrics only)."""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from pca_e2e import oc
from pca_e2e import opencode as ocapi

from pca_perf.config import REPO_DIR, REPO_URL, opencode_timeout_secs, user_namespace
from pca_perf.gpu import GpuSampler
from pca_perf.guardrails import scrape_overhead_seconds
from pca_perf.metrics import StageResult, WorkerResult, stage_from_workers, usage_token_parts
from pca_perf.semantic_router import scrape_hop_seconds

log = logging.getLogger(__name__)

# Load probe only — not a real Model Registry integration.
# Intentionally tiny so the ladder finishes in minutes, not hours.
OPENCODE_PROMPT = (
    f"You are working in {REPO_DIR}. "
    "Create a single file named MODEL_REGISTRY_TODO.md at the repo root with "
    "a short TODO list (3–5 bullets) about adding OpenShift AI Model Registry "
    "later. Do not implement Model Registry. Do not edit other files. "
    "Do not ask questions — create the file and stop."
)


def _running_workspace_pod(namespace: str, dw: dict) -> str:
    wid = (dw.get("status") or {}).get("devworkspaceId") or ""
    if wid:
        try:
            return oc.find_workspace_pod(namespace, wid)
        except oc.OcError:
            pass
    result = oc.run_oc("get", "pods", "-n", namespace, "-o", "json", check=False)
    items = json.loads(result.stdout or "{}").get("items") or []
    for item in items:
        if (item.get("status") or {}).get("phase") != "Running":
            continue
        name = (item.get("metadata") or {}).get("name") or ""
        if name.startswith("workspace"):
            return name
    raise oc.OcError(f"no Running workspace pod in {namespace}")


def _model_ids_from_devworkspace(dw: dict) -> tuple[str, str] | None:
    env = oc.devworkspace_env(dw)
    model = (env.get("VLLM_MODEL_ID") or env.get("OPENAI_MODEL") or "").strip()
    if not model:
        return None
    return "vllm", model


_REPO_CLONE_TIMEOUT_SECS = 300
_REPO_CLONE_ATTEMPTS = 2


def _ensure_repo(namespace: str, pod: str) -> None:
    """Clone the load-probe repo once per workspace. Re-clone is ~12s of overhead."""
    script = f"""
set -euo pipefail
if [ -d {REPO_DIR}/.git ]; then
  rm -f {REPO_DIR}/MODEL_REGISTRY_TODO.md
  test -d {REPO_DIR}
  exit 0
fi
rm -rf {REPO_DIR}
GIT_TERMINAL_PROMPT=0 git clone --depth 1 {REPO_URL} {REPO_DIR}
test -d {REPO_DIR}
"""
    last_exc: Exception | None = None
    for attempt in range(1, _REPO_CLONE_ATTEMPTS + 1):
        try:
            oc.exec_in_pod(
                namespace,
                pod,
                "bash",
                "-lc",
                script,
                timeout=_REPO_CLONE_TIMEOUT_SECS,
            )
            return
        except oc.OcError as exc:
            last_exc = exc
            log.warning(
                "repo clone attempt %s/%s failed in %s: %s",
                attempt,
                _REPO_CLONE_ATTEMPTS,
                namespace,
                exc,
            )
    assert last_exc is not None
    raise last_exc


def _run_one_user(user_index: int) -> WorkerResult:
    ns = user_namespace(user_index)
    timeout = opencode_timeout_secs()
    worker_start = time.perf_counter()
    try:
        # --- setup (counted in overhead / makespan, not in generation_secs) ---
        dw = oc.find_opencode_devworkspace(ns)
        if dw is None:
            return WorkerResult(ok=False, error=f"{ns}: no OpenCode DevWorkspace")
        name = (dw.get("metadata") or {}).get("name") or ""
        if not oc.devworkspace_is_running(dw):
            dw = oc.ensure_devworkspace_started(ns, name, timeout_secs=600)
        pod = _running_workspace_pod(ns, dw)
        password = oc.secret_data("opencode-web-password", "password", ns)
        _ensure_repo(ns, pod)
        resolved = _model_ids_from_devworkspace(dw)
        if resolved is None:
            provider_id, model_id = ocapi.resolve_model_ids(ns, pod)
        else:
            provider_id, model_id = resolved

        with oc.PortForward(ns, pod, 4096) as pf:
            with ocapi.OpenCodeClient(
                pf.base_url,
                password,
                directory=REPO_DIR,
                timeout_secs=timeout,
            ) as client:
                client.health()
                session = client.create_session(
                    f"pca-perf-model-registry-u{user_index}"
                )
                sid = session["id"]

                # --- generation window (timed: first SSE frame → turn done) ---
                resp: dict[str, Any]
                generation_secs: float
                gen_start: float
                gen_end: float
                prefill_secs: float
                decode_secs: float
                (
                    resp,
                    generation_secs,
                    gen_start,
                    gen_end,
                    prefill_secs,
                    decode_secs,
                ) = client.run_turn_with_generation_timing(
                    sid,
                    OPENCODE_PROMPT,
                    provider_id=provider_id,
                    model_id=model_id,
                    timeout=timeout,
                )
                llm_calls, output_from_steps = client.count_llm_calls(sid)
                durations = client.llm_call_durations_secs(sid)
                first_call = durations[0] if durations else None
                last_call = durations[-1] if len(durations) >= 2 else None
                _, completion_from_resp, _ = usage_token_parts(resp)
                completion_tokens = output_from_steps or completion_from_resp
                if llm_calls == 0 and completion_tokens > 0:
                    # Fallback when message list shape is unexpected but usage exists.
                    llm_calls = 1
                worker_end = time.perf_counter()
                return WorkerResult(
                    ok=True,
                    generation_secs=generation_secs,
                    gen_start=gen_start,
                    gen_end=gen_end,
                    worker_start=worker_start,
                    worker_end=worker_end,
                    prefill_secs=prefill_secs,
                    decode_secs=decode_secs,
                    completion_tokens=completion_tokens,
                    llm_calls=llm_calls,
                    first_llm_call_secs=first_call,
                    last_llm_call_secs=last_call,
                )
    except Exception as exc:  # noqa: BLE001 — aggregate into stage result
        log.exception("OpenCode user %s failed", user_index)
        return WorkerResult(ok=False, error=f"{ns}: {exc}")


def run_opencode_stage(*, ai_namespace: str, n: int) -> StageResult:
    workers: list[WorkerResult] = []
    before_overhead = scrape_overhead_seconds(ai_namespace)
    before_hop = scrape_hop_seconds(ai_namespace)
    with GpuSampler(ai_namespace) as sampler:
        with ThreadPoolExecutor(max_workers=n) as pool:
            futures = {
                pool.submit(_run_one_user, i): i for i in range(1, n + 1)
            }
            for fut in as_completed(futures):
                workers.append(fut.result())
        peak_gpu = sampler.peak_util_pct
        gen_starts = [
            w.gen_start for w in workers if w.ok and w.gen_start is not None
        ]
        gen_ends = [w.gen_end for w in workers if w.ok and w.gen_end is not None]
        if gen_starts and gen_ends:
            # Mean over active generation window only (not clone/setup idle).
            mean_gpu = sampler.mean_util_pct_between(
                min(gen_starts), max(gen_ends)
            )
        else:
            mean_gpu = sampler.mean_util_pct
    after_overhead = scrape_overhead_seconds(ai_namespace)
    after_hop = scrape_hop_seconds(ai_namespace)
    ok = sum(1 for w in workers if w.ok)
    guardrails_overhead = None
    if (
        before_overhead is not None
        and after_overhead is not None
        and after_overhead >= before_overhead
        and ok
    ):
        guardrails_overhead = (after_overhead - before_overhead) / ok
    semantic_router_hop = None
    if (
        before_hop is not None
        and after_hop is not None
        and after_hop >= before_hop
        and ok
    ):
        semantic_router_hop = (after_hop - before_hop) / ok
    return stage_from_workers(
        n,
        workers,
        gpu_util_pct=peak_gpu,
        gpu_mean_util_pct=mean_gpu,
        guardrails_overhead_secs=guardrails_overhead,
        semantic_router_hop_secs=semantic_router_hop,
    )
