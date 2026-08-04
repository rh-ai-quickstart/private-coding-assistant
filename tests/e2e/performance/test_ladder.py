"""Scalability ladder: for each N, concurrent OpenCode users."""

from __future__ import annotations

import pytest

from pca_perf.metrics import StageResult, format_report
from pca_perf.opencode_run import run_opencode_stage

pytestmark = pytest.mark.performance


def test_performance_ladder(
    perf_n: int,
    ai_ns: str,
    perf_namespaces: list[str],
    results_sink: list[StageResult],
) -> None:
    """Run OpenCode load at concurrency N.

    Metrics: e2e/req output tok/s, makespan, gen span, overhead, LLM calls.
    OpenCode only creates MODEL_REGISTRY_TODO.md (load probe). Missing
    DevSpaces fail at setup.
    """
    del perf_namespaces  # validated by fixture; opencode_run uses dev-user1..N

    opencode = run_opencode_stage(ai_namespace=ai_ns, n=perf_n)
    results_sink.append(opencode)
    print(f"\n{format_report([opencode])}\n", flush=True)

    # Soft signal: report stays the deliverable; fail the row only if every
    # OpenCode user errored (otherwise the ladder is still useful).
    if opencode.ok == 0 and opencode.failed > 0:
        pytest.fail(
            f"OpenCode stage N={perf_n}: all {opencode.failed} users failed. "
            f"Errors: {opencode.errors[:5]}"
        )
