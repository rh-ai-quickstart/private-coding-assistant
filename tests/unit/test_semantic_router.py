"""Helm-render checks for official vLLM Semantic Router config."""

from __future__ import annotations

import subprocess

import yaml

from helm_pca import (
    AI_SERVING,
    LLMD_SVC,
    REPO_ROOT,
    _docs,
    _helm_template,
    _named,
)


def _sr_config(docs: list[dict]) -> dict:
    cm = _named(docs, "ConfigMap", "pca-semantic-router-config")
    return yaml.safe_load(cm["data"]["config.yaml"])


def _sr_envoy(docs: list[dict]) -> str:
    cm = _named(docs, "ConfigMap", "pca-semantic-router-config")
    return cm["data"]["envoy.yaml"]


def _maybe_named(docs: list[dict], kind: str, name: str) -> dict | None:
    for doc in docs:
        if doc.get("kind") == kind and doc.get("metadata", {}).get("name") == name:
            return doc
    return None


def test_sr_off_skips_hop():
    docs = _docs(
        _helm_template(AI_SERVING, ["--set", "tlsJob.enabled=false"]),
    )
    assert _maybe_named(docs, "Deployment", "pca-semantic-router") is None
    assert _maybe_named(docs, "ConfigMap", "pca-semantic-router-config") is None
    assert all(
        (d.get("kind"), d.get("metadata", {}).get("name")) != ("Service", "pca-llm-upstream")
        for d in docs
    )


def test_sr_on_no_extras_pins_local_qwen():
    docs = _docs(
        _helm_template(
            AI_SERVING,
            [
                "--set",
                "semanticRouter.enabled=true",
                "--set",
                "tlsJob.enabled=false",
            ],
        )
    )
    cfg = _sr_config(docs)
    names = [m["name"] for m in cfg["providers"]["models"]]
    assert names == ["local"]
    local = cfg["providers"]["models"][0]
    assert local["provider_model_id"] == "Qwen/Qwen3.6-35B-A3B-FP8"
    assert f"{LLMD_SVC}.ai-serving.svc.cluster.local:80" in local["backend_refs"][0]["endpoint"]
    signals = cfg["routing"].get("signals") or {}
    assert not signals.get("complexity")
    assert not signals.get("keywords")
    decisions = {d["name"]: d for d in cfg["routing"]["decisions"]}
    assert set(decisions) == {"default_route"}
    assert decisions["default_route"]["modelRefs"][0]["model"] == "local"
    deploy = _named(docs, "Deployment", "pca-semantic-router")
    containers = {
        c["name"] for c in deploy["spec"]["template"]["spec"]["containers"]
    }
    assert containers == {"envoy", "extproc"}
    envoy = _sr_envoy(docs)
    assert "/tokenize" in envoy
    assert "/detokenize" in envoy
    svc = _named(docs, "Service", "pca-semantic-router")
    ports = {p["name"]: p for p in svc["spec"]["ports"]}
    assert ports["http"]["port"] == 80
    assert ports["http"]["targetPort"] == 8800


def test_sr_on_one_extra_routes_code_and_hard_to_strongest():
    docs = _docs(
        _helm_template(
            AI_SERVING,
            [
                "--set",
                "semanticRouter.enabled=true",
                "--set",
                "tlsJob.enabled=false",
                "--set-json",
                'semanticRouter.models=[{"name":"cloud","strength":"strong","endpoint":"https://api.example.com/v1","modelId":"gpt-4o"}]',
                "--set-json",
                'semanticRouter.apiKeysJson={"cloud":"sk-test"}',
            ],
        )
    )
    cfg = _sr_config(docs)
    names = [m["name"] for m in cfg["providers"]["models"]]
    assert names == ["local", "cloud"]
    decisions = {d["name"]: d for d in cfg["routing"]["decisions"]}
    assert decisions["strong_route"]["modelRefs"][0]["model"] == "cloud"
    conds = decisions["strong_route"]["rules"]["conditions"]
    types = {(c.get("type"), c.get("name")) for c in conds}
    assert ("keyword", "code") in types
    assert ("complexity", "task_complexity:hard") in types
    assert decisions["easy_route"]["modelRefs"][0]["model"] == "local"
    easy_types = [
        (c.get("type"), c.get("name"), c.get("operator"))
        for c in decisions["easy_route"]["rules"]["conditions"]
    ]
    assert ("complexity", "task_complexity:easy", None) in easy_types
    assert any(c.get("operator") == "NOT" for c in decisions["easy_route"]["rules"]["conditions"])
    assert decisions["default_route"]["modelRefs"][0]["model"] == "local"
    secret = _named(docs, "Secret", "pca-sr-cloud")
    assert secret["stringData"]["api-key"] == "sk-test"
    env_names = {
        e["name"]
        for c in _named(docs, "Deployment", "pca-semantic-router")["spec"]["template"]["spec"][
            "containers"
        ]
        if c["name"] == "extproc"
        for e in c.get("env") or []
    }
    assert "SR_KEY_cloud" in env_names
    envoy = _sr_envoy(docs)
    assert "cloud_cluster" in envoy
    assert "api.example.com" in envoy


def test_mismatched_sr_enable_flags_fail_render():
    result = subprocess.run(
        [
            "helm",
            "template",
            "test",
            str(AI_SERVING),
            "--set",
            "observability.enabled=false",
            "--set",
            "semanticRouter.enabled=true",
            "--set",
            "global.semanticRouter.enabled=false",
            "--set",
            "tlsJob.enabled=false",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "semanticRouter.enabled and global.semanticRouter.enabled must match" in (
        result.stderr + result.stdout
    )


def test_extra_without_api_key_fails_render():
    result = subprocess.run(
        [
            "helm",
            "template",
            "test",
            str(AI_SERVING),
            "--set",
            "observability.enabled=false",
            "--set",
            "semanticRouter.enabled=true",
            "--set",
            "global.semanticRouter.enabled=true",
            "--set",
            "tlsJob.enabled=false",
            "--set-json",
            'semanticRouter.models=[{"name":"cloud","strength":"strong","endpoint":"https://api.example.com/v1","modelId":"gpt-4o"}]',
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "needs semanticRouter.apiKeysJson" in (result.stderr + result.stdout)


def test_sr_string_false_skips_hop():
    docs = _docs(
        _helm_template(
            AI_SERVING,
            [
                "--set-string",
                "semanticRouter.enabled=false",
                "--set-string",
                "global.semanticRouter.enabled=false",
                "--set",
                "tlsJob.enabled=false",
            ],
        )
    )
    assert _maybe_named(docs, "Deployment", "pca-semantic-router") is None
    assert _maybe_named(docs, "ConfigMap", "pca-semantic-router-config") is None


def _ai_serving_helm_params(extra: list[str]) -> list[dict]:
    result = subprocess.run(
        [
            "helm",
            "template",
            "root",
            str(REPO_ROOT / "charts" / "pca-app-of-apps"),
            "--set",
            "gitops.cloud=rosa",
            *extra,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    for doc in yaml.safe_load_all(result.stdout):
        if not isinstance(doc, dict):
            continue
        if doc.get("kind") != "Application":
            continue
        if (doc.get("metadata") or {}).get("name") != "pca-ai-serving":
            continue
        src = (doc.get("spec") or {}).get("source") or {}
        helm = src.get("helm") or {}
        return list(helm.get("parameters") or [])
    raise AssertionError("Application/pca-ai-serving missing")


def test_app_of_apps_empty_enable_leaves_overlay():
    names = {p["name"] for p in _ai_serving_helm_params([])}
    assert "semanticRouter.enabled" not in names
    assert "global.semanticRouter.enabled" not in names


def test_app_of_apps_string_false_forwards_override():
    params = {
        p["name"]: p["value"]
        for p in _ai_serving_helm_params(
            ["--set-string", "aiServing.semanticRouterEnabled=false"]
        )
    }
    assert params["semanticRouter.enabled"] == "false"
    assert params["global.semanticRouter.enabled"] == "false"
