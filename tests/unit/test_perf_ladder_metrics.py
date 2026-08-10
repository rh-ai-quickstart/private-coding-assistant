"""Unit tests for OpenCode ladder stage aggregation (prefill / decode)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_PERF_DIR = Path(__file__).resolve().parents[1] / "e2e" / "performance" / "pca_perf"
_METRICS_PATH = _PERF_DIR / "metrics.py"
_GPU_PATH = _PERF_DIR / "gpu.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    # gpu.py imports pca_e2e + pca_perf.config; stub if absent so _mean can
    # still be tested without the e2e package path.
    if name.endswith("gpu"):
        import types

        if "pca_e2e" not in sys.modules:
            stub = types.ModuleType("pca_e2e")
            stub_oc = types.ModuleType("pca_e2e.oc")
            stub.oc = stub_oc
            sys.modules["pca_e2e"] = stub
            sys.modules["pca_e2e.oc"] = stub_oc
        if "pca_perf" not in sys.modules:
            stub_perf = types.ModuleType("pca_perf")
            stub_cfg = types.ModuleType("pca_perf.config")
            stub_cfg.model_name = lambda: "qwen3-coder"
            stub_perf.config = stub_cfg
            sys.modules["pca_perf"] = stub_perf
            sys.modules["pca_perf.config"] = stub_cfg
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def metrics():
    return _load("pca_perf_metrics", _METRICS_PATH)


@pytest.fixture(scope="module")
def gpu_mod():
    return _load("pca_perf_gpu", _GPU_PATH)


def test_stage_averages_prefill_decode_ok_only(metrics):
    WorkerResult = metrics.WorkerResult
    stage_from_workers = metrics.stage_from_workers
    workers = [
        WorkerResult(
            ok=True,
            generation_secs=10.0,
            prefill_secs=2.0,
            decode_secs=8.0,
            completion_tokens=100,
        ),
        WorkerResult(
            ok=True,
            generation_secs=12.0,
            prefill_secs=4.0,
            decode_secs=6.0,
            completion_tokens=80,
        ),
        WorkerResult(ok=False, error="timed out"),
    ]
    stage = stage_from_workers(3, workers)
    assert stage.ok == 2
    assert stage.failed == 1
    assert stage.avg_prefill_secs == 3.0
    assert stage.avg_decode_secs == 7.0


def test_format_report_includes_prefill_decode_columns(metrics):
    WorkerResult = metrics.WorkerResult
    stage_from_workers = metrics.stage_from_workers
    format_report = metrics.format_report
    stage = stage_from_workers(
        1,
        [
            WorkerResult(
                ok=True,
                generation_secs=5.0,
                prefill_secs=1.5,
                decode_secs=3.5,
                completion_tokens=50,
                worker_start=0.0,
                worker_end=6.0,
                gen_start=1.0,
                gen_end=6.0,
            )
        ],
        gpu_util_pct=40.0,
        gpu_mean_util_pct=22.0,
    )
    report = format_report([stage])
    assert "avg prefill time per user (sec)" in report
    assert "avg decode time per user (sec)" in report
    assert "peak GPU utilization (%)" in report
    assert "mean GPU utilization (%)" in report
    assert "| 1.5 |" in report.replace(" ", "") or "1.5" in report
    assert "3.5" in report
    assert "40" in report
    assert "22" in report


def test_gpu_mean(gpu_mod):
    assert gpu_mod._mean([]) is None
    assert gpu_mod._mean([10.0]) == 10.0
    assert gpu_mod._mean([10.0, 30.0, 20.0]) == 20.0
    assert gpu_mod._mean([10.0, 20.0]) == 15.0
