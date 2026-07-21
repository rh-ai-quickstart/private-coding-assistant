"""Assert core (and optional) cluster objects are ready."""

from __future__ import annotations

import json

import pytest

from pca_smoke import oc, urls

pytestmark = pytest.mark.readiness


def test_llminferenceservice_ready(ai_namespace: str, oc_user: str) -> None:
    del oc_user
    assert oc.resource_exists(
        "llminferenceservice", urls.LLMIS_NAME, namespace=ai_namespace
    ), f"LLMInferenceService/{urls.LLMIS_NAME} missing in {ai_namespace}"
    status = oc.condition_status(
        "llminferenceservice", urls.LLMIS_NAME, "Ready", ai_namespace
    )
    assert status == "True", f"LLMInferenceService/{urls.LLMIS_NAME} Ready={status!r}"


def test_gateway_accepted(ai_namespace: str) -> None:
    assert oc.resource_exists(
        "gateway", urls.GATEWAY_NAME, namespace=ai_namespace
    ), f"Gateway/{urls.GATEWAY_NAME} missing in {ai_namespace}"
    status = oc.condition_status("gateway", urls.GATEWAY_NAME, "Accepted", ai_namespace)
    assert status == "True", f"Gateway/{urls.GATEWAY_NAME} Accepted={status!r}"


def test_ai_gateway_accepted_if_present(ai_namespace: str) -> None:
    """RHCL front door is optional until charts are synced with aiGateway.enabled."""
    if not oc.resource_exists(
        "gateway", urls.AI_GATEWAY_NAME, namespace=ai_namespace
    ):
        pytest.skip(f"Gateway/{urls.AI_GATEWAY_NAME} not deployed in {ai_namespace}")
    status = oc.condition_status(
        "gateway", urls.AI_GATEWAY_NAME, "Accepted", ai_namespace
    )
    assert status == "True", f"Gateway/{urls.AI_GATEWAY_NAME} Accepted={status!r}"
    assert oc.resource_exists(
        "httproute", urls.AI_GATEWAY_HTTP_ROUTE, namespace=ai_namespace
    ), f"HTTPRoute/{urls.AI_GATEWAY_HTTP_ROUTE} missing in {ai_namespace}"
    assert oc.resource_exists(
        "authpolicy", urls.AI_GATEWAY_AUTH_POLICY, namespace=ai_namespace
    ), f"AuthPolicy/{urls.AI_GATEWAY_AUTH_POLICY} missing in {ai_namespace}"


def test_model_cache_pvc_bound(ai_namespace: str) -> None:
    assert oc.resource_exists(
        "pvc", urls.PVC_NAME, namespace=ai_namespace
    ), f"PVC/{urls.PVC_NAME} missing in {ai_namespace}"
    phase = oc.pvc_phase(urls.PVC_NAME, ai_namespace)
    assert phase == "Bound", f"PVC/{urls.PVC_NAME} phase={phase!r}"


def test_predictor_pods_running(ai_namespace: str) -> None:
    # LLMInferenceService workload pods (not classic InferenceService label).
    result = oc.run_oc(
        "get",
        "pods",
        "-n",
        ai_namespace,
        "-l",
        f"app.kubernetes.io/name={urls.LLMIS_NAME},app.kubernetes.io/component=llminferenceservice-workload",
        "-o",
        "json",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    items = json.loads(result.stdout).get("items") or []
    if not items:
        result = oc.run_oc(
            "get",
            "pods",
            "-n",
            ai_namespace,
            "-l",
            f"app.kubernetes.io/name={urls.LLMIS_NAME}",
            "-o",
            "json",
            check=False,
        )
        items = json.loads(result.stdout).get("items") or []
    assert items, f"no workload pods for {urls.LLMIS_NAME} in {ai_namespace}"
    not_ready = []
    for pod in items:
        name = pod["metadata"]["name"]
        phase = pod.get("status", {}).get("phase")
        ready_conds = [
            c.get("status") == "True"
            for c in (pod.get("status", {}).get("conditions") or [])
            if c.get("type") == "Ready"
        ]
        if phase != "Running" or (ready_conds and not ready_conds[0]):
            not_ready.append(f"{name}(phase={phase})")
    assert not not_ready, f"predictor pods not ready: {', '.join(not_ready)}"


def test_grafana_deploy_available(ai_namespace: str) -> None:
    if not oc.resource_exists("deploy", urls.GRAFANA_NAME, namespace=ai_namespace):
        pytest.skip("Grafana not deployed")
    assert oc.deployment_available(
        urls.GRAFANA_NAME, ai_namespace
    ), f"deploy/{urls.GRAFANA_NAME} not Available"


def test_langfuse_pods_if_present(ai_namespace: str) -> None:
    if not oc.resource_exists("route", urls.LANGFUSE_ROUTE, namespace=ai_namespace):
        pytest.skip("Langfuse not deployed")
    assert oc.resource_exists(
        "svc", "pca-langfuse-web", namespace=ai_namespace
    ), "pca-langfuse-web service missing"


def test_otel_deploy_if_present(ai_namespace: str) -> None:
    if not oc.resource_exists("deploy", urls.OTEL_NAME, namespace=ai_namespace):
        pytest.skip("OTel Collector not deployed")
    assert oc.deployment_available(
        urls.OTEL_NAME, ai_namespace
    ), f"deploy/{urls.OTEL_NAME} not Available"


def test_guardrails_proxy_if_present(ai_namespace: str) -> None:
    if not oc.resource_exists("svc", urls.GUARDRAILS_PROXY, namespace=ai_namespace):
        pytest.skip("Guardrails not deployed")
    result = oc.run_oc(
        "get",
        "pods",
        "-n",
        ai_namespace,
        "-l",
        "app.kubernetes.io/name=guardrails-proxy",
        "-o",
        "jsonpath={.items[*].status.phase}",
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        result = oc.run_oc(
            "get",
            "pods",
            "-n",
            ai_namespace,
            "-o",
            "name",
            check=False,
        )
        names = [n for n in result.stdout.splitlines() if "guardrails-proxy" in n]
        assert names, "guardrails-proxy pods not found"
    else:
        phases = result.stdout.split()
        assert phases and all(p == "Running" for p in phases), f"guardrails pods: {phases}"


def test_devworkspace_if_dev_namespace(require_dev_namespace: str) -> None:
    ns = require_dev_namespace
    result = oc.run_oc(
        "get",
        "devworkspace",
        "-n",
        ns,
        "-o",
        "json",
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"cannot list DevWorkspaces in {ns}: {result.stderr.strip()}")
    items = json.loads(result.stdout).get("items") or []
    if not items:
        pytest.skip(f"no DevWorkspace in {ns}")
    phases = [i.get("status", {}).get("phase") for i in items]
    assert items, f"DevWorkspace list empty in {ns} (phases={phases})"
