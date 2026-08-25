"""Helm-render checks for guardrails hop order and Semantic Router."""

from __future__ import annotations

import json
import subprocess

import yaml

from helm_pca import (
    AI_SERVING,
    DEVSPACES,
    LLMD_SVC,
    MAAS_HOST,
    PLATFORM,
    _backend_names,
    _docs,
    _helm_template,
    _httproute,
    _llm_upstream_url,
    _named,
    _orchestrator_host,
    _rule_first_paths,
)


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
    assert _rule_first_paths(route) == [
        "/v1/chat/completions",
        "/local/v1",
        "/v1/models",
        "/v1",
    ]
    backends = _backend_names(route)
    assert "/v1/chat/completions->guardrails-proxy:8080" in backends
    proxy_deploy = _named(docs, "Deployment", "guardrails-proxy")
    script_cm = _named(docs, "ConfigMap", "guardrails-proxy-script")
    assert "sse_http.py" in script_cm.get("data", {})
    assert "guardrails_outcome.py" in script_cm.get("data", {})
    assert "guardrails_langfuse.py" in script_cm.get("data", {})
    assert "guardrails_proxy.py" in script_cm.get("data", {})
    proxy_env = {
        e["name"]: e.get("value")
        for e in proxy_deploy["spec"]["template"]["spec"]["containers"][0]["env"]
        if "value" in e
    }
    assert proxy_env["LLM_UPSTREAM_URL"] == f"http://{LLMD_SVC}.ai-serving.svc.cluster.local:80"
    detectors = json.loads(proxy_env["DETECTORS_JSON"])
    assert detectors.get("output") in ({}, None)
    assert "regex" not in (detectors.get("output") or {})
    gw_cfg = _named(docs, "ConfigMap", "pca-guardrails-gateway-config")
    gw_yaml = (gw_cfg.get("data") or {}).get("config.yaml", "")
    assert gw_yaml.count("output: false") >= 2
    assert "output: true" not in gw_yaml
    assert f"/v1/models->{LLMD_SVC}:80" in backends
    assert f"/v1/models/->{LLMD_SVC}:80" in backends
    assert f"/v1->{LLMD_SVC}:80" in backends
    assert "/local/v1->" + LLMD_SVC + ":80" in backends
    cfg = _orchestrator_host(docs)
    assert f"hostname: {LLMD_SVC}." in cfg
    assert "port: 80" in cfg
    assert "qwen3-coder-kserve-workload-svc" not in cfg
    assert "client_ca_cert_path" not in cfg
    assert "pca-llm-upstream" not in rendered
    assert "pca-ai-gateway-local" not in rendered
    filt = _named(docs, "EnvoyFilter", "pca-maas-models-first")
    assert filt["metadata"]["namespace"] == "openshift-ingress"
    patch = filt["spec"]["configPatches"][0]["patch"]
    assert patch["operation"] == "INSERT_FIRST"
    assert patch["value"]["match"]["path"] == "/v1/models"
    assert f"outbound|80||{LLMD_SVC}." in patch["value"]["route"]["cluster"]
    tfc = patch["value"]["typed_per_filter_config"]
    assert tfc["envoy.filters.http.ext_proc.bbr"]["disabled"] is True
    wasm = "extensions.istio.io/wasmplugin/openshift-ingress.kuadrant-maas-default-gateway"
    assert tfc[wasm]["disabled"] is True
    auth = _named(docs, "AuthPolicy", "pca-maas-apikey")
    assert auth["spec"]["targetRef"]["name"] == "pca-maas-front-door"
    auth_ids = (auth["spec"].get("overrides") or {}).get("rules", {}).get("authentication", {})
    assert "pca-maas-apikey" in auth_ids
    assert "pca-ai-gateway-apikey" not in auth_ids


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
    assert f"/v1/chat/completions->{LLMD_SVC}:80" in backends
    assert f"/v1/models->{LLMD_SVC}:80" in backends
    assert f"/v1/models/->{LLMD_SVC}:80" in backends
    assert f"/v1->{LLMD_SVC}:80" in backends
    assert "name: guardrails-proxy" not in rendered


def test_httproute_chat_goes_to_sr_when_guardrails_off_and_sr_on():
    rendered = _helm_template(
        AI_SERVING,
        [
            "--set",
            "guardrails.enabled=false",
            "--set",
            "semanticRouter.enabled=true",
            "--set",
            "tlsJob.enabled=false",
        ],
    )
    docs = _docs(rendered)
    backends = _backend_names(_httproute(docs))
    assert "/v1/chat/completions->pca-semantic-router:80" in backends
    assert f"/v1/models->{LLMD_SVC}:80" in backends
    assert f"/v1/models/->{LLMD_SVC}:80" in backends
    assert f"/local/v1->{LLMD_SVC}:80" in backends
    deploy = _named(docs, "Deployment", "pca-semantic-router")
    env = {
        item["name"]: item.get("value")
        for item in deploy["spec"]["template"]["spec"]["containers"][0]["env"]
        if "value" in item
    }
    assert env["ROUTE_MODE"] == "pin-local"
    assert env["LOCAL_BASE_URL"] == f"http://{LLMD_SVC}.ai-serving.svc.cluster.local:80/v1"
    script_cm = _named(docs, "ConfigMap", "pca-semantic-router-script")
    assert "sse_http.py" in script_cm.get("data", {})
    assert "semantic_router.py" in script_cm.get("data", {})


def test_orchestrator_pins_local_when_sr_off_and_points_at_sr_when_on():
    off = _docs(
        _helm_template(
            AI_SERVING,
            ["--set", "guardrails.enabled=true", "--set", "tlsJob.enabled=false"],
        )
    )
    assert _llm_upstream_url(off) == f"http://{LLMD_SVC}.ai-serving.svc.cluster.local:80"
    assert f"hostname: {LLMD_SVC}." in _orchestrator_host(off)
    on = _docs(
        _helm_template(
            AI_SERVING,
            [
                "--set",
                "guardrails.enabled=true",
                "--set",
                "semanticRouter.enabled=true",
                "--set",
                "tlsJob.enabled=false",
            ],
        )
    )
    assert _llm_upstream_url(on) == (
        "http://pca-semantic-router.ai-serving.svc.cluster.local:80"
    )
    cfg = _orchestrator_host(on)
    assert "hostname: pca-semantic-router." in cfg
    backends = _backend_names(_httproute(on))
    assert "/v1/chat/completions->guardrails-proxy:8080" in backends
    assert "/v1/chat/completions->pca-semantic-router:80" not in backends


def test_prompt_injection_detector_shares_pvc_sync_wave():
    rendered = _helm_template(
        AI_SERVING,
        ["--set", "guardrails.enabled=true", "--set", "tlsJob.enabled=false"],
    )
    docs = _docs(rendered)
    pvc = _named(docs, "PersistentVolumeClaim", "detector-model-cache")
    isvc = _named(docs, "InferenceService", "pi-detector")
    assert pvc["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"] == "0"
    assert isvc["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"] == "0"


def test_aro_overlays_keep_guardrails_on():
    serving = _helm_template(
        AI_SERVING,
        [
            "-f",
            str(AI_SERVING / "values-aro.yaml"),
            "--set",
            "observability.enabled=false",
            "--set",
            "tlsJob.enabled=false",
        ],
    )
    serving_docs = _docs(serving)
    backends = _backend_names(_httproute(serving_docs))
    assert "/v1/chat/completions->guardrails-proxy:8080" in backends
    _named(serving_docs, "Service", "guardrails-proxy")
    _named(serving_docs, "Deployment", "guardrails-proxy")

    platform = subprocess.run(
        [
            "helm",
            "template",
            "test",
            str(PLATFORM),
            "-f",
            str(PLATFORM / "values-aro.yaml"),
            "--set",
            "mcp.enabled=false",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    dsc = _named(_docs(platform), "DataScienceCluster", "default-dsc")
    assert dsc["spec"]["components"]["trustyai"]["managementState"] == "Managed"

    spaces = _helm_template(
        DEVSPACES,
        [
            "-f",
            str(DEVSPACES / "values-aro.yaml"),
            "--set",
            "devspacesGlobalConfig.enabled=false",
            "--set",
            "opencodeBuild.enabled=false",
            "--set",
            "dashboardSamples.enabled=false",
        ],
    )
    overlay = yaml.safe_load((DEVSPACES / "values-aro.yaml").read_text()) or {}
    assert overlay.get("guardrails", {}).get("enabled") is True
    assert f"{MAAS_HOST}/v1" in spaces
    assert "name: guardrails-proxy" not in spaces


def test_rosa_overlay_enables_langfuse_and_semantic_router():
    rendered = _helm_template(
        AI_SERVING,
        [
            "-f",
            str(AI_SERVING / "values-rosa.yaml"),
            "--set",
            "observability.enabled=true",
            "--set",
            "tlsJob.enabled=false",
        ],
    )
    docs = _docs(rendered)
    backends = _backend_names(_httproute(docs))
    assert "/v1/chat/completions->guardrails-proxy:8080" in backends
    _named(docs, "Deployment", "pca-semantic-router")
    _named(docs, "Service", "pca-semantic-router")
    assert "hostname: pca-semantic-router." in _orchestrator_host(docs)
    kinds = {(d.get("kind"), d.get("metadata", {}).get("name")) for d in docs}
    assert ("Deployment", "pca-otel-collector") in kinds
    assert any(name and str(name).startswith("pca-langfuse") for _, name in kinds)
