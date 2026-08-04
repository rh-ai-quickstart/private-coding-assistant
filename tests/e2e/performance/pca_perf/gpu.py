"""Best-effort GPU utilization from a vLLM / workload pod."""

from __future__ import annotations

import logging

from pca_e2e import oc

log = logging.getLogger(__name__)


def gpu_utilization_percent(ai_namespace: str) -> float | None:
    """Return average nvidia-smi GPU util %, or None if unavailable."""
    result = oc.run_oc(
        "get",
        "pods",
        "-n",
        ai_namespace,
        "-l",
        "app.kubernetes.io/component=llminferenceservice-workload",
        "-o",
        "jsonpath={.items[?(@.status.phase=='Running')].metadata.name}",
        check=False,
    )
    names = (result.stdout or "").split()
    if not names:
        # Custom runtime InferenceService predictor pods
        result = oc.run_oc(
            "get",
            "pods",
            "-n",
            ai_namespace,
            "-l",
            "serving.kserve.io/inferenceservice=qwen3-coder",
            "-o",
            "jsonpath={.items[?(@.status.phase=='Running')].metadata.name}",
            check=False,
        )
        names = (result.stdout or "").split()
    if not names:
        log.info("no workload pods found for GPU util in %s", ai_namespace)
        return None

    pod = names[0]
    smi = oc.run_oc(
        "exec",
        "-n",
        ai_namespace,
        pod,
        "--",
        "nvidia-smi",
        "--query-gpu=utilization.gpu",
        "--format=csv,noheader,nounits",
        check=False,
        timeout=30,
    )
    if smi.returncode != 0:
        log.info("nvidia-smi failed in %s/%s: %s", ai_namespace, pod, smi.stderr)
        return None
    values: list[float] = []
    for line in (smi.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            values.append(float(line))
        except ValueError:
            continue
    if not values:
        return None
    return sum(values) / len(values)
