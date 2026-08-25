"""Stage-level guardrails proxy overhead from Prometheus /metrics."""

from __future__ import annotations

from pca_perf.prometheus import parse_counter, scrape_counter

OVERHEAD_METRIC = "pca_guardrails_overhead_seconds_total"


def parse_overhead_seconds(text: str) -> float | None:
    """Return the overhead counter from Prometheus text, or None if absent."""
    return parse_counter(text, OVERHEAD_METRIC)


def scrape_overhead_seconds(ai_namespace: str) -> float | None:
    """Read overhead seconds from deploy/guardrails-proxy. None if scrape fails."""
    return scrape_counter(
        ai_namespace,
        "deploy/guardrails-proxy",
        "proxy",
        OVERHEAD_METRIC,
        label="guardrails",
    )
