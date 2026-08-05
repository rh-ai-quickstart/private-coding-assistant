"""Unit tests for OpenCode ladder stage aggregation (prefill / decode)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_METRICS_PATH = (
    Path(__file__).resolve().parents[1]
    / "e2e"
    / "performance"
    / "pca_perf"
    / "metrics.py"
)


@pytest.fixture(scope="module")
def metrics():
    spec = importlib.util.spec_from_file_location("pca_perf_metrics", _METRICS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["pca_perf_metrics"] = module
    spec.loader.exec_module(module)
    return module


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
    )
    report = format_report([stage])
    assert "avg prefill time per user (sec)" in report
    assert "avg decode time per user (sec)" in report
    assert "| 1.5 |" in report.replace(" ", "") or "1.5" in report
    assert "3.5" in report
