"""DevSpaces config + harness request (requires DEV_NAMESPACE)."""

from __future__ import annotations

import json

import pytest

from pca_smoke import oc, urls

pytestmark = pytest.mark.devspaces


def _assert_gateway_or_proxy_url(text: str, ai_namespace: str, config_name: str) -> None:
    """IDE configs should hit RHCL (default), llm-d escape hatch, or guardrails."""
    assert (
        f"{urls.AI_GATEWAY_NAME}-{urls.GATEWAY_CLASS}.{ai_namespace}" in text
        or f"{urls.GATEWAY_NAME}-{urls.GATEWAY_CLASS}.{ai_namespace}" in text
        or "guardrails-proxy" in text
        or urls.GUARDRAILS_PROXY in text
    ), f"{config_name} does not reference RHCL / llm-d / guardrails:\n{text[:500]}"


def test_continue_configmap(require_dev_namespace: str, ai_namespace: str) -> None:
    ns = require_dev_namespace
    assert oc.resource_exists(
        "configmap", "continue-config", namespace=ns
    ), f"continue-config missing in {ns}"
    data = oc.configmap_data("continue-config", ns)
    yaml_text = data.get("config.yaml") or ""
    assert "X-PCA-User" in yaml_text or "X-PCA-DevSpace" in yaml_text, yaml_text[:500]
    _assert_gateway_or_proxy_url(yaml_text, ai_namespace, "continue-config")


def test_roo_code_configmap(require_dev_namespace: str, ai_namespace: str) -> None:
    ns = require_dev_namespace
    assert oc.resource_exists(
        "configmap", "roo-code-provider-config", namespace=ns
    ), f"roo-code-provider-config missing in {ns}"
    data = oc.configmap_data("roo-code-provider-config", ns)
    joined = "\n".join(data.values())
    assert "X-PCA-User" in joined or "openAiHeaders" in joined or "X-PCA" in joined, (
        f"roo config missing attribution headers: {list(data.keys())}"
    )
    _assert_gateway_or_proxy_url(joined, ai_namespace, "roo-code-provider-config")


def test_cline_configmap(require_dev_namespace: str, ai_namespace: str) -> None:
    ns = require_dev_namespace
    if not oc.resource_exists("configmap", "cline-provider-config", namespace=ns):
        pytest.skip(f"cline-provider-config missing in {ns}")
    data = oc.configmap_data("cline-provider-config", ns)
    joined = "\n".join(data.values())
    assert "X-PCA-User" in joined or "X-PCA-DevSpace" in joined or "openAiHeaders" in joined, (
        f"cline config missing attribution headers: {list(data.keys())}"
    )
    _assert_gateway_or_proxy_url(joined, ai_namespace, "cline-provider-config")


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
    """Simulate Roo/Continue: chat with X-PCA-* via default IDE path (RHCL) or llm-d."""
    ns = require_dev_namespace
    headers: dict[str, str] = {
        "X-PCA-User": "smoke-test",
        "X-PCA-DevSpace": ns,
    }
    # Default IDE path is RHCL + API key; fall back to llm-d when front door absent.
    if oc.resource_exists("gateway", urls.AI_GATEWAY_NAME, namespace=ai_namespace):
        if not oc.resource_exists(
            "secret", urls.AI_GATEWAY_APIKEY_SECRET, namespace=ns
        ):
            pytest.skip(
                f"RHCL gateway present but secret/{urls.AI_GATEWAY_APIKEY_SECRET} "
                f"missing in {ns}"
            )
        base = urls.ai_gateway_v1(ai_namespace)
        api_key = oc.secret_data(
            urls.AI_GATEWAY_APIKEY_SECRET, urls.AI_GATEWAY_APIKEY_KEY, ns
        )
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        base = gateway_v1

    status, body = oc.in_cluster_http(
        ai_namespace,
        f"{base}/chat/completions",
        method="POST",
        headers=headers,
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
