"""Unit checks for GPU util parsing / sampler aggregates (no cluster)."""

from __future__ import annotations

from pca_perf.gpu import GpuSampler, _mean, parse_nvidia_smi_util_lines


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


def test_mean_helper() -> None:
    assert _mean([]) is None
    assert _mean([10.0]) == 10.0
    assert _mean([0.0, 100.0, 50.0]) == 50.0
    assert _mean([0.0, 100.0]) == 50.0


def test_gpu_sampler_peak_and_mean_from_samples() -> None:
    """Peak/mean over a short-burst pattern (idle → spike → idle)."""
    sampler = GpuSampler("unused-ns")
    for util in (0.0, 0.0, 87.0, 100.0, 0.0):
        sampler._append(util)
    assert sampler.peak_util_pct == 100.0
    # Full-stage mean is pulled down by idle zeros: (0+0+87+100+0)/5.
    assert sampler.mean_util_pct == (0.0 + 0.0 + 87.0 + 100.0 + 0.0) / 5.0


def test_gpu_sampler_mean_between_generation_window() -> None:
    """Mean in gen window ignores setup idle before/after decode."""
    sampler = GpuSampler("unused-ns")
    # Many setup idle samples, then a short generation burst, then idle again.
    for t in (1.0, 2.0, 3.0, 4.0, 5.0):
        sampler._append(0.0, t=t)
    sampler._append(87.0, t=10.0)
    sampler._append(100.0, t=11.0)
    sampler._append(90.0, t=12.0)
    sampler._append(0.0, t=20.0)
    assert sampler.peak_util_pct == 100.0
    # Full-stage mean is still dominated by idle zeros.
    assert sampler.mean_util_pct is not None
    assert sampler.mean_util_pct < 40.0
    # Active generation window only → high mean (not ~0).
    window_mean = sampler.mean_util_pct_between(10.0, 12.0)
    assert window_mean is not None
    assert abs(window_mean - (87.0 + 100.0 + 90.0) / 3.0) < 0.1
    assert abs((sampler.mean_util_pct_between(9.5, 12.5) or 0.0) - 92.333) < 0.1
    assert sampler.mean_util_pct_between(0.0, 0.5) is None


def test_gpu_sampler_empty_is_none() -> None:
    sampler = GpuSampler("unused-ns")
    assert sampler.peak_util_pct is None
    assert sampler.mean_util_pct is None
    assert sampler.mean_util_pct_between(0.0, 1.0) is None
