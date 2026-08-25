"""Helm-render helpers for pca-ai-serving / pca-devspaces / pca-platform-config."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_SERVING = REPO_ROOT / "charts" / "pca-ai-serving"
DEVSPACES = REPO_ROOT / "charts" / "pca-devspaces"
PLATFORM = REPO_ROOT / "charts" / "pca-platform-config"

MAAS_HOST = "maas-default-gateway-data-science-gateway-class.openshift-ingress.svc.cluster.local"
LLMD_SVC = "llm-d-gateway-data-science-gateway-class"


def _with_sr_global(extra: list[str]) -> list[str]:
    """Copy semanticRouter.enabled onto global so the guardrails subchart sees it."""
    out = list(extra)
    sr = None
    has_global = False
    i = 0
    while i < len(out):
        if out[i] == "--set" and i + 1 < len(out):
            key, _, val = out[i + 1].partition("=")
            if key == "semanticRouter.enabled":
                sr = val
            elif key == "global.semanticRouter.enabled":
                has_global = True
            i += 2
            continue
        i += 1
    if sr is not None and not has_global:
        out.extend(["--set", f"global.semanticRouter.enabled={sr}"])
    return out


def _helm_template(chart: Path, extra: list[str]) -> str:
    extra = _with_sr_global(extra)
    result = subprocess.run(
        [
            "helm",
            "template",
            "test",
            str(chart),
            "--set",
            "observability.enabled=false",
            *extra,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _docs(rendered: str) -> list[dict]:
    out = []
    for doc in yaml.safe_load_all(rendered):
        if isinstance(doc, dict):
            out.append(doc)
    return out


def _named(docs: list[dict], kind: str, name: str) -> dict:
    for doc in docs:
        if doc.get("kind") == kind and doc.get("metadata", {}).get("name") == name:
            return doc
    raise AssertionError(f"{kind}/{name} missing")


def _httproute(docs: list[dict]) -> dict:
    return _named(docs, "HTTPRoute", "pca-maas-front-door")


def _backend_names(route: dict) -> list[str]:
    names = []
    for rule in route.get("spec", {}).get("rules") or []:
        for match in rule.get("matches") or []:
            path = (match.get("path") or {}).get("value")
            for ref in rule.get("backendRefs") or []:
                names.append(f"{path}->{ref.get('name')}:{ref.get('port')}")
    return names


def _front_door_rules() -> list[dict]:
    path = AI_SERVING / "files" / "maas-front-door-rules.yaml"
    return yaml.safe_load(path.read_text())["rules"]


def _authz_istio_route_names(namespace: str = "ai-serving") -> list[str]:
    return [
        f"{namespace}.pca-maas-front-door.{i}"
        for i, rule in enumerate(_front_door_rules())
        if rule.get("auth")
    ]


def _rule_first_paths(route: dict) -> list[str]:
    """First path match per HTTPRoute rule — EnvoyFilter authz uses these indices."""
    paths = []
    for rule in route.get("spec", {}).get("rules") or []:
        matches = rule.get("matches") or []
        if matches:
            paths.append((matches[0].get("path") or {}).get("value"))
    return paths


def _orchestrator_host(docs: list[dict]) -> str:
    orch = _named(docs, "ConfigMap", "pca-guardrails-config")
    return orch.get("data", {}).get("config.yaml") or ""


def _llm_upstream_url(docs: list[dict]) -> str:
    proxy = _named(docs, "Deployment", "guardrails-proxy")
    env = {
        e["name"]: e.get("value")
        for e in proxy["spec"]["template"]["spec"]["containers"][0]["env"]
        if "value" in e
    }
    return env.get("LLM_UPSTREAM_URL") or ""
