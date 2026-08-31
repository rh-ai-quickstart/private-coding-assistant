"""Stage-level semantic-router hop seconds from Prometheus /metrics."""

from __future__ import annotations

from pca_perf.prometheus import parse_counter, scrape_counter

HOP_METRIC = "pca_semantic_router_hop_seconds_total"


def parse_hop_seconds(text: str) -> float | None:
    """Return the hop counter from Prometheus text, or None if absent."""
    return parse_counter(text, HOP_METRIC)


def scrape_hop_seconds(ai_namespace: str) -> float | None:
    """Read hop seconds from deploy/pca-semantic-router. None if scrape fails.

    Official vLLM SR does not export pca_semantic_router_hop_seconds_total;
    this stays None until that mapping exists.
    """
    return scrape_counter(
        ai_namespace,
        "deploy/pca-semantic-router",
        "extproc",
        HOP_METRIC,
        label="semantic-router",
    )
