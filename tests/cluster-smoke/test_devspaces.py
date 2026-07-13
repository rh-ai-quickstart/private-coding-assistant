"""DevSpaces config + harness request (requires DEV_NAMESPACE)."""

from __future__ import annotations

import json

import pytest

from pca_smoke import oc

pytestmark = pytest.mark.devspaces


def test_continue_configmap(require_dev_namespace: str, ai_namespace: str) -> None:
    ns = require_dev_namespace
    assert oc.resource_exists(
        "configmap", "continue-config", namespace=ns
    ), f"continue-config missing in {ns}"
    data = oc.configmap_data("continue-config", ns)
    yaml_text = data.get("config.yaml") or ""
    assert "X-PCA-User" in yaml_text or "X-PCA-DevSpace" in yaml_text, yaml_text[:500]
    assert (
        f"llm-d-gateway-data-science-gateway-class.{ai_namespace}" in yaml_text
        or "guardrails-proxy" in yaml_text
        or "/v1" in yaml_text
    ), f"continue config does not reference gateway/proxy:\n{yaml_text[:500]}"


def test_roo_code_configmap(require_dev_namespace: str) -> None:
    ns = require_dev_namespace
    assert oc.resource_exists(
        "configmap", "roo-code-provider-config", namespace=ns
    ), f"roo-code-provider-config missing in {ns}"
    data = oc.configmap_data("roo-code-provider-config", ns)
    joined = "\n".join(data.values())
    assert "X-PCA-User" in joined or "openAiHeaders" in joined or "X-PCA" in joined, (
        f"roo config missing attribution headers: {list(data.keys())}"
    )


def test_devworkspace_exists(require_dev_namespace: str) -> None:
    ns = require_dev_namespace
    result = oc.run_oc("get", "devworkspace", "-n", ns, "-o", "json", check=False)
    assert result.returncode == 0, result.stderr
    items = json.loads(result.stdout).get("items") or []
    assert items, f"no DevWorkspace in {ns}"


def test_harness_chat_with_attribution(
    require_dev_namespace: str,
    ai_namespace: str,
    gateway_v1: str,
    model_id: str,
) -> None:
    """Simulate Roo/Continue: chat completion with X-PCA-* headers."""
    ns = require_dev_namespace
    status, body = oc.in_cluster_http(
        ai_namespace,
        f"{gateway_v1}/chat/completions",
        method="POST",
        headers={
            "X-PCA-User": "smoke-test",
            "X-PCA-DevSpace": ns,
        },
        json_body={
            "model": model_id,
            "messages": [{"role": "user", "content": "Reply with the single word pong."}],
            "stream": False,
            "max_tokens": 32,
        },
        timeout_secs=180,
    )
    assert status == 200, f"harness chat returned {status}: {body!r}"
    assert isinstance(body, dict), body
    choices = body.get("choices") or []
    assert choices, body
    content = oc.message_text(choices[0])
    assert str(content).strip(), f"empty harness response: {body}"
