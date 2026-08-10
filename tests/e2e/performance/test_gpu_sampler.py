"""Unit checks for GPU util parsing / sampler aggregates (no cluster)."""

from __future__ import annotations

from pca_perf.gpu import GpuSampler, _median, parse_nvidia_smi_util_lines


def test_parse_nvidia_smi_util_single_line() -> None:
    assert parse_nvidia_smi_util_lines("87\n") == 87.0
    assert parse_nvidia_smi_util_lines("  100  ") == 100.0


def test_parse_nvidia_smi_util_multi_gpu_average() -> None:
    assert parse_nvidia_smi_util_lines("80\n90\n") == 85.0
    assert parse_nvidia_smi_util_lines("80, 90") == 85.0


def test_parse_nvidia_smi_util_empty_or_junk() -> None:
    assert parse_nvidia_smi_util_lines("") is None
    assert parse_nvidia_smi_util_lines("\n\n") is None
    assert parse_nvidia_smi_util_lines("not-a-number") is None


def test_median_helper() -> None:
    assert _median([]) is None
    assert _median([10.0]) == 10.0
    assert _median([0.0, 100.0, 50.0]) == 50.0
    assert _median([0.0, 100.0]) == 50.0


def test_gpu_sampler_peak_and_median_from_samples() -> None:
    """Peak/median over a short-burst pattern (idle → spike → idle)."""
    sampler = GpuSampler("unused-ns")
    for util in (0.0, 0.0, 87.0, 100.0, 0.0):
        sampler._append(util)
    assert sampler.peak_util_pct == 100.0
    assert sampler.median_util_pct == 0.0


def test_gpu_sampler_empty_is_none() -> None:
    sampler = GpuSampler("unused-ns")
    assert sampler.peak_util_pct is None
    assert sampler.median_util_pct is None
