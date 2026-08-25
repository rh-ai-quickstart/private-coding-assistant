"""Helm-render checks for the GuideLLM capacity Job."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
CHART = REPO / "charts" / "pca-benchmarks"


def _template(*extra: str) -> list[dict]:
    result = subprocess.run(
        [
            "helm",
            "template",
            "t",
            str(CHART),
            "--set",
            "enabled=true",
            "--set",
            "namespace=ai-serving",
            *extra,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return [doc for doc in yaml.safe_load_all(result.stdout) if isinstance(doc, dict)]


def _job(docs: list[dict]) -> dict:
    for doc in docs:
        if doc.get("kind") == "Job" and doc.get("metadata", {}).get("name") == "guidellm-capacity":
            return doc
    raise AssertionError("Job/guidellm-capacity missing")


def _container(job: dict) -> dict:
    return job["spec"]["template"]["spec"]["containers"][0]


def _env(container: dict, name: str) -> str:
    for item in container.get("env") or []:
        if item.get("name") == name:
            return str(item.get("value") or "")
    raise AssertionError(f"env {name} missing")


def test_guidellm_cpu_request_fits_busy_workers() -> None:
    container = _container(_job(_template()))
    assert container["resources"]["requests"]["cpu"] == "200m"
    assert container["resources"]["requests"]["memory"] == "1Gi"


def test_streams_set_json_keeps_comma_list() -> None:
    container = _container(_job(_template("--set-json", 'streams="1,4"')))
    assert _env(container, "GUIDELLM_STREAMS") == "1,4"
