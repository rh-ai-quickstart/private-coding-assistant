"""Best-effort GPU utilization from a vLLM / workload pod."""

from __future__ import annotations

import logging
import threading

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


class GpuSampler:
    """Background nvidia-smi sampler; exposes peak util during a stage."""

    def __init__(self, ai_namespace: str, *, interval_secs: float = 2.0) -> None:
        self.ai_namespace = ai_namespace
        self.interval_secs = interval_secs
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._samples: list[float] = []
        self._lock = threading.Lock()

    def __enter__(self) -> GpuSampler:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="gpu-sampler", daemon=True
        )
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval_secs + 10.0)
            self._thread = None

    @property
    def peak_util_pct(self) -> float | None:
        with self._lock:
            if not self._samples:
                return None
            return max(self._samples)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                util = gpu_utilization_percent(self.ai_namespace)
            except Exception as exc:  # noqa: BLE001 — sampling must not fail the stage
                log.info("GPU sample failed: %s", exc)
                util = None
            if util is not None:
                with self._lock:
                    self._samples.append(util)
            self._stop.wait(self.interval_secs)
        # One last sample after the load ends.
        try:
            util = gpu_utilization_percent(self.ai_namespace)
        except Exception:  # noqa: BLE001
            util = None
        if util is not None:
            with self._lock:
                self._samples.append(util)
