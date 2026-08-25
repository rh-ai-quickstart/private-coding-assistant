"""Prometheus text parse + in-cluster /metrics scrape."""

from __future__ import annotations

import logging

from pca_e2e import oc

log = logging.getLogger(__name__)

_SCRAPE = (
    "import urllib.request; "
    "print(urllib.request.urlopen('http://127.0.0.1:8080/metrics').read().decode())"
)


def parse_counter(text: str, metric: str) -> float | None:
    """Return a Prometheus counter value, or None if the metric is absent."""
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[0] == metric:
            try:
                return float(parts[1])
            except ValueError:
                return None
    return None


def scrape_counter(
    ai_namespace: str,
    deploy: str,
    container: str,
    metric: str,
    *,
    label: str,
) -> float | None:
    """Read `metric` from a Deployment's /metrics. None if scrape fails."""
    result = oc.run_oc(
        "exec",
        "-n",
        ai_namespace,
        deploy,
        "-c",
        container,
        "--",
        "python3",
        "-c",
        _SCRAPE,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        log.info(
            "%s metrics scrape failed: %s",
            label,
            (result.stderr or "").strip(),
        )
        return None
    return parse_counter(result.stdout or "", metric)
