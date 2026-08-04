"""Concurrent OpenCode agent load (generation-timed; metrics only)."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from pca_e2e import oc
from pca_e2e import opencode as ocapi

from pca_perf.config import REPO_DIR, REPO_URL, opencode_timeout_secs, user_namespace
from pca_perf.gpu import GpuSampler
from pca_perf.metrics import WorkerResult, stage_from_workers, usage_token_parts

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


def _clone_repo(namespace: str, pod: str) -> None:
    oc.exec_in_pod(
        namespace,
        pod,
        "bash",
        "-lc",
        f"""
set -euo pipefail
rm -rf {REPO_DIR}
git clone --depth 1 {REPO_URL} {REPO_DIR}
test -d {REPO_DIR}
""",
        timeout=180,
    )


def _run_one_user(user_index: int) -> WorkerResult:
    ns = user_namespace(user_index)
    timeout = opencode_timeout_secs()
    try:
        # --- setup (NOT timed) ---
        dw = oc.find_opencode_devworkspace(ns)
        if dw is None:
            return WorkerResult(ok=False, error=f"{ns}: no OpenCode DevWorkspace")
        name = (dw.get("metadata") or {}).get("name") or ""
        dw = oc.ensure_devworkspace_started(ns, name, timeout_secs=600)
        pod = _running_workspace_pod(ns, dw)
        password = oc.secret_data("opencode-web-password", "password", ns)
        _clone_repo(ns, pod)
        provider_id, model_id = ocapi.resolve_model_ids(ns, pod)

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
                resp, generation_secs, gen_start, gen_end = (
                    client.run_turn_with_generation_timing(
                        sid,
                        OPENCODE_PROMPT,
                        provider_id=provider_id,
                        model_id=model_id,
                        timeout=timeout,
                    )
                )
                prompt_tokens, completion_tokens, tokens = usage_token_parts(resp)
                return WorkerResult(
                    ok=True,
                    tokens=tokens,
                    generation_secs=generation_secs,
                    gen_start=gen_start,
                    gen_end=gen_end,
                    prompt_tokens=prompt_tokens or None,
                    completion_tokens=completion_tokens or None,
                )
    except Exception as exc:  # noqa: BLE001 — aggregate into stage result
        log.exception("OpenCode user %s failed", user_index)
        return WorkerResult(ok=False, error=f"{ns}: {exc}")


def run_opencode_stage(*, ai_namespace: str, n: int):
    workers: list[WorkerResult] = []
    with GpuSampler(ai_namespace) as sampler:
        with ThreadPoolExecutor(max_workers=n) as pool:
            futures = {
                pool.submit(_run_one_user, i): i for i in range(1, n + 1)
            }
            for fut in as_completed(futures):
                workers.append(fut.result())
        peak_gpu = sampler.peak_util_pct
    return stage_from_workers("opencode", n, workers, gpu_util_pct=peak_gpu)
