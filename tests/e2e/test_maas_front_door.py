"""Plan 6/7: IDE URL is MaaS only and pca-ai-gateway is gone."""

from __future__ import annotations

import json

import pytest

from pca_e2e import oc
from pca_e2e import routes

pytestmark = pytest.mark.maas


def test_is_maas_openai_base_url_accepts_maas_only() -> None:
    assert oc.is_maas_openai_base_url("https://maas.apps.example.com/v1")
    assert oc.is_maas_openai_base_url(
        "https://maas-default-gateway-data-science-gateway-class."
        "openshift-ingress.svc.cluster.local/v1"
    )
    assert not oc.is_maas_openai_base_url(
        "https://pca-ai-gateway-data-science-gateway-class."
        "ai-serving.svc.cluster.local/v1"
    )
    assert not oc.is_maas_openai_base_url(
        "https://llm-d-gateway-data-science-gateway-class."
        "ai-serving.svc.cluster.local/v1"
    )
    assert routes.origin_from_base_url("https://maas.apps.example.com/v1") == (
        "https://maas.apps.example.com"
    )


def test_opencode_openai_base_url_is_maas(require_dev_namespace: str) -> None:
    ns = require_dev_namespace
    dw = oc.find_opencode_devworkspace(ns)
    assert dw is not None, f"no OpenCode DevWorkspace in {ns}"
    base = oc.devworkspace_env(dw).get("OPENAI_BASE_URL", "")
    oc.assert_openai_base_url_reaches_maas(base)
    assert "pca-ai-gateway" not in base.lower(), base


def test_pca_ai_gateway_absent(ai_namespace: str) -> None:
    assert not oc.resource_exists(
        "gateway", "pca-ai-gateway", namespace=ai_namespace
    ), f"Gateway/pca-ai-gateway still exists in {ai_namespace}"
    result = oc.run_oc("get", "gateway", "-A", "-o", "json", check=False)
    assert result.returncode == 0, result.stderr
    items = json.loads(result.stdout or "{}").get("items") or []
    leftovers = [
        f"{(item.get('metadata') or {}).get('namespace')}/"
        f"{(item.get('metadata') or {}).get('name')}"
        for item in items
        if (item.get("metadata") or {}).get("name") == "pca-ai-gateway"
    ]
    assert not leftovers, f"Gateway/pca-ai-gateway still exists: {leftovers}"
