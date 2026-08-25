"""Helm-render checks for gateway-first guardrails routing."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_SERVING = REPO_ROOT / "charts" / "pca-ai-serving"
DEVSPACES = REPO_ROOT / "charts" / "pca-devspaces"


def _helm_template(chart: Path, extra: list[str]) -> str:
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


def _httproute(docs: list[dict]) -> dict:
    for doc in docs:
        if doc.get("kind") == "HTTPRoute" and doc.get("metadata", {}).get("name") == "pca-maas-front-door":
            return doc
    raise AssertionError("HTTPRoute/pca-maas-front-door missing")


def _backend_names(route: dict) -> list[str]:
    names = []
    for rule in route.get("spec", {}).get("rules") or []:
        for match in rule.get("matches") or []:
            path = (match.get("path") or {}).get("value")
            for ref in rule.get("backendRefs") or []:
                names.append(f"{path}->{ref.get('name')}:{ref.get('port')}")
    return names


def test_httproute_chat_goes_to_proxy_when_guardrails_on():
    rendered = _helm_template(
        AI_SERVING,
        [
            "--set",
            "guardrails.enabled=true",
            "--set",
            "tlsJob.enabled=false",
        ],
    )
    docs = _docs(rendered)
    route = _httproute(docs)
    assert route["spec"]["parentRefs"][0]["name"] == "maas-default-gateway"
    assert route["spec"]["parentRefs"][0]["namespace"] == "openshift-ingress"
    backends = _backend_names(route)
    assert "/v1/chat/completions->guardrails-proxy:8080" in backends
    assert "/v1->llm-d-gateway-data-science-gateway-class:80" in backends
    orch = None
    for doc in docs:
        if (
            doc.get("kind") == "ConfigMap"
            and doc.get("metadata", {}).get("name") == "pca-guardrails-config"
        ):
            orch = doc
            break
    assert orch is not None, "pca-guardrails-config missing"
    cfg = orch.get("data", {}).get("config.yaml") or ""
    assert "hostname: llm-d-gateway-data-science-gateway-class." in cfg
    assert "port: 80" in cfg
    assert "qwen3-coder-kserve-workload-svc" not in cfg
    assert "client_ca_cert_path" not in cfg


def test_httproute_chat_goes_to_llmd_when_guardrails_off():
    rendered = _helm_template(
        AI_SERVING,
        [
            "--set",
            "guardrails.enabled=false",
            "--set",
            "tlsJob.enabled=false",
        ],
    )
    route = _httproute(_docs(rendered))
    backends = _backend_names(route)
    assert "/v1/chat/completions->guardrails-proxy:8080" not in backends
    assert "/v1->llm-d-gateway-data-science-gateway-class:80" in backends
    assert "name: guardrails-proxy" not in rendered


def test_devspaces_chat_url_is_gateway_with_api_key_when_guardrails_on():
    rendered = _helm_template(
        DEVSPACES,
        [
            "--set",
            "guardrails.enabled=true",
            "--set",
            "aiServingNamespace=ai-serving",
            "--set",
            "devspacesGlobalConfig.enabled=false",
            "--set",
            "opencodeBuild.enabled=false",
            "--set",
            "dashboardSamples.enabled=false",
            "--set",
            "devspaces[0].type=continue",
        ],
    )
    docs = _docs(rendered)

    secrets = [
        doc
        for doc in docs
        if doc.get("kind") == "Secret" and doc.get("metadata", {}).get("name") == "pca-ai-gw-apikey"
    ]
    assert secrets, "pca-ai-gw-apikey Secret missing"

    continue_cm = None
    for doc in docs:
        if doc.get("kind") == "ConfigMap" and doc.get("metadata", {}).get("name") == "continue-config":
            continue_cm = doc
            break
    assert continue_cm is not None, "continue-config ConfigMap missing"
    config_yaml = continue_cm.get("data", {}).get("config.yaml") or ""
    assert "pca-ai-gateway-data-science-gateway-class.ai-serving.svc.cluster.local/v1" in config_yaml
    assert "llm-d-gateway-data-science-gateway-class.ai-serving.svc.cluster.local/v1" in config_yaml
    assert "guardrails-proxy" not in config_yaml

    config = yaml.safe_load(config_yaml)
    assert config["models"][0]["apiKey"] != "EMPTY"
    # tabAutocompleteModel talks to llm-d directly (unauthenticated) when guardrails is
    # on, so it must not carry the real gateway key (see continue-configmaps.yaml).
    assert config["tabAutocompleteModel"]["apiKey"] == "EMPTY"
