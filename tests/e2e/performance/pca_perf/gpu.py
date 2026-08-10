"""Best-effort GPU utilization from a vLLM / workload pod."""

from __future__ import annotations

import logging
import subprocess
import threading
import time

from pca_e2e import oc
from pca_perf.config import model_name

log = logging.getLogger(__name__)


def parse_nvidia_smi_util_lines(text: str) -> float | None:
    """Parse nvidia-smi utilization.gpu CSV lines into an average percent."""
    values: list[float] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # One GPU per line; also accept comma-separated multi-value lines.
        for part in line.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                values.append(float(part))
            except ValueError:
                continue
    if not values:
        return None
    return sum(values) / len(values)


def find_workload_pod(ai_namespace: str) -> str | None:
    """Return a Running vLLM / InferenceService workload pod name, or None."""
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
            f"serving.kserve.io/inferenceservice={model_name()}",
            "-o",
            "jsonpath={.items[?(@.status.phase=='Running')].metadata.name}",
            check=False,
        )
        names = (result.stdout or "").split()
    if not names:
        log.info("no workload pods found for GPU util in %s", ai_namespace)
        return None
    return names[0]


def gpu_utilization_percent(
    ai_namespace: str, *, pod: str | None = None
) -> float | None:
    """Return average nvidia-smi GPU util %, or None if unavailable."""
    if pod is None:
        pod = find_workload_pod(ai_namespace)
    if not pod:
        return None

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
    return parse_nvidia_smi_util_lines(smi.stdout or "")


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    mid = len(xs) // 2
    if len(xs) % 2 == 1:
        return xs[mid]
    return (xs[mid - 1] + xs[mid]) / 2.0


class GpuSampler:
    """Background nvidia-smi sampler; exposes peak/median util during a stage.

    Prefers one long-lived ``nvidia-smi -l 1`` stream (catches short decode
    bursts). Falls back to periodic one-shot ``oc exec`` polls if streaming
    cannot start.
    """

    def __init__(self, ai_namespace: str, *, interval_secs: float = 2.0) -> None:
        self.ai_namespace = ai_namespace
        # Used only by the one-shot fallback poll loop.
        self.interval_secs = interval_secs
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._samples: list[float] = []
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[str] | None = None

    def __enter__(self) -> GpuSampler:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="gpu-sampler", daemon=True
        )
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._terminate_stream()
        if self._thread is not None:
            self._thread.join(timeout=self.interval_secs + 15.0)
            self._thread = None

    @property
    def peak_util_pct(self) -> float | None:
        with self._lock:
            if not self._samples:
                return None
            return max(self._samples)

    @property
    def median_util_pct(self) -> float | None:
        with self._lock:
            return _median(self._samples)

    def _append(self, util: float) -> None:
        with self._lock:
            self._samples.append(util)

    def _terminate_stream(self) -> None:
        proc = self._proc
        if proc is None or proc.poll() is not None:
            self._proc = None
            return
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        self._proc = None

    def _start_stream(self, pod: str) -> subprocess.Popen[str] | None:
        try:
            proc = subprocess.Popen(
                [
                    "oc",
                    "exec",
                    "-n",
                    self.ai_namespace,
                    pod,
                    "--",
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu",
                    "--format=csv,noheader,nounits",
                    "-l",
                    "1",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            log.info("failed to start nvidia-smi stream: %s", exc)
            return None
        # Brief wait: if oc/exec fails immediately, fall back to polling.
        time.sleep(0.5)
        if proc.poll() is not None:
            err = ""
            if proc.stderr is not None:
                err = proc.stderr.read() or ""
            log.info(
                "nvidia-smi stream exited early in %s/%s: %s",
                self.ai_namespace,
                pod,
                err.strip(),
            )
            return None
        self._proc = proc
        return proc

    def _run_stream(self, proc: subprocess.Popen[str]) -> bool:
        """Read streaming nvidia-smi lines until stop. Return True if any sample."""
        got_sample = False
        assert proc.stdout is not None
        while not self._stop.is_set():
            line = proc.stdout.readline()
            if line == "":
                # EOF — process ended
                break
            util = parse_nvidia_smi_util_lines(line)
            if util is not None:
                self._append(util)
                got_sample = True
        return got_sample

    def _run_poll_loop(self, pod: str | None) -> None:
        """Fallback: one-shot oc exec samples (slower; may miss short bursts)."""
        while not self._stop.is_set():
            try:
                util = gpu_utilization_percent(self.ai_namespace, pod=pod)
            except Exception as exc:  # noqa: BLE001 — sampling must not fail the stage
                log.info("GPU sample failed: %s", exc)
                util = None
            if util is not None:
                self._append(util)
            self._stop.wait(self.interval_secs)
        try:
            util = gpu_utilization_percent(self.ai_namespace, pod=pod)
        except Exception:  # noqa: BLE001
            util = None
        if util is not None:
            self._append(util)

    def _run(self) -> None:
        pod: str | None
        try:
            pod = find_workload_pod(self.ai_namespace)
        except Exception as exc:  # noqa: BLE001
            log.info("GPU pod lookup failed: %s", exc)
            pod = None

        if pod:
            proc = self._start_stream(pod)
            if proc is not None:
                try:
                    self._run_stream(proc)
                finally:
                    self._terminate_stream()
                if self._stop.is_set():
                    return
                log.info("nvidia-smi stream ended early; falling back to polls")

        log.info("GPU util falling back to one-shot nvidia-smi polls")
        self._run_poll_loop(pod)
