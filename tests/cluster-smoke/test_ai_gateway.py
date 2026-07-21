"""RHCL AI Gateway smoke tests (skipped when Gateway/pca-ai-gateway is absent)."""

from __future__ import annotations

import pytest

from pca_smoke import oc, urls

pytestmark = pytest.mark.ai_gateway

AI_GATEWAY_APIKEY_LABEL = "app.kubernetes.io/component=pca-ai-gateway-apikey"


@pytest.fixture(autouse=True)
def _require_ai_gateway(require_ai_gateway: str) -> None:
    del require_ai_gateway


def test_gateway_accepted(ai_namespace: str) -> None:
    status = oc.condition_status(
        "gateway", urls.AI_GATEWAY_NAME, "Accepted", ai_namespace
    )
    assert status == "True", f"Gateway/{urls.AI_GATEWAY_NAME} Accepted={status!r}"


def test_httproute_exists(ai_namespace: str) -> None:
    assert oc.resource_exists(
        "httproute", urls.AI_GATEWAY_HTTP_ROUTE, namespace=ai_namespace
    ), f"HTTPRoute/{urls.AI_GATEWAY_HTTP_ROUTE} missing in {ai_namespace}"


def test_authpolicy_exists(ai_namespace: str) -> None:
    assert oc.resource_exists(
        "authpolicy", urls.AI_GATEWAY_AUTH_POLICY, namespace=ai_namespace
    ), f"AuthPolicy/{urls.AI_GATEWAY_AUTH_POLICY} missing in {ai_namespace}"


def test_chat_completions_rejects_missing_api_key(
    ai_namespace: str, ai_gateway_v1: str, model_id: str
) -> None:
    status, body = oc.in_cluster_http(
        ai_namespace,
        f"{ai_gateway_v1}/chat/completions",
        method="POST",
        json_body={
            "model": model_id,
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": False,
            "max_tokens": 8,
        },
        timeout_secs=60,
    )
    assert status in (401, 403), f"missing API key expected 401/403, got {status}: {body!r}"


def test_chat_completions_rejects_invalid_api_key(
    ai_namespace: str, ai_gateway_v1: str, model_id: str
) -> None:
    status, body = oc.in_cluster_http(
        ai_namespace,
        f"{ai_gateway_v1}/chat/completions",
        method="POST",
        headers={"Authorization": "Bearer invalid-smoke-test-key"},
        json_body={
            "model": model_id,
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": False,
            "max_tokens": 8,
        },
        timeout_secs=60,
    )
    assert status in (401, 403), f"invalid API key expected 401/403, got {status}: {body!r}"


def test_dev_namespace_apikey_secret(require_dev_namespace: str) -> None:
    ns = require_dev_namespace
    assert oc.resource_exists(
        "secret", urls.AI_GATEWAY_APIKEY_SECRET, namespace=ns
    ), f"secret/{urls.AI_GATEWAY_APIKEY_SECRET} missing in {ns}"
    api_key = oc.secret_data(
        urls.AI_GATEWAY_APIKEY_SECRET, urls.AI_GATEWAY_APIKEY_KEY, ns
    )
    assert api_key.strip(), (
        f"secret/{urls.AI_GATEWAY_APIKEY_SECRET} key "
        f"{urls.AI_GATEWAY_APIKEY_KEY} is empty in {ns}"
    )


def test_ai_namespace_mirror_apikey_secret(
    ai_namespace: str, require_dev_namespace: str
) -> None:
    del require_dev_namespace
    names = oc.list_resource_names(
        "secret", ai_namespace, label_selector=AI_GATEWAY_APIKEY_LABEL
    )
    assert names, (
        f"no secrets labeled {AI_GATEWAY_APIKEY_LABEL!r} in {ai_namespace}"
    )
    has_key = False
    for name in names:
        try:
            value = oc.secret_data(name, urls.AI_GATEWAY_APIKEY_KEY, ai_namespace)
        except oc.OcError:
            continue
        if value.strip():
            has_key = True
            break
    assert has_key, (
        f"mirror secrets {names} in {ai_namespace} lack non-empty "
        f"{urls.AI_GATEWAY_APIKEY_KEY!r}"
    )


def test_chat_completions_with_valid_api_key(
    ai_namespace: str,
    ai_gateway_v1: str,
    model_id: str,
    require_dev_namespace: str,
) -> None:
    api_key = oc.secret_data(
        urls.AI_GATEWAY_APIKEY_SECRET,
        urls.AI_GATEWAY_APIKEY_KEY,
        require_dev_namespace,
    )
    status, body = oc.in_cluster_http(
        ai_namespace,
        f"{ai_gateway_v1}/chat/completions",
        method="POST",
        headers={"Authorization": f"Bearer {api_key}"},
        json_body={
            "model": model_id,
            "messages": [{"role": "user", "content": "Reply with the single word pong."}],
            "stream": False,
            "max_tokens": 32,
        },
        timeout_secs=180,
    )
    assert status == 200, f"chat/completions returned {status}: {body!r}"
    assert isinstance(body, dict), body
    choices = body.get("choices") or []
    assert choices, body
    content = oc.message_text(choices[0])
    assert str(content).strip(), f"empty assistant message: {body}"


def _ai_gateway_host(ai_namespace: str) -> str:
    return f"{urls.AI_GATEWAY_NAME}-{urls.GATEWAY_CLASS}.{ai_namespace}"


_API_KEY_FIELD_NAMES = ("apiKey", "openAiApiKey", "openAiCompatibleApiKey")


def _iter_api_key_field_values(text: str):
    """Yield API key values from YAML or JSON IDE config snippets."""
    for line in text.splitlines():
        stripped = line.strip().rstrip(",")
        for name in _API_KEY_FIELD_NAMES:
            # YAML: apiKey: value
            if stripped.startswith(f"{name}:"):
                _, _, raw = stripped.partition(":")
                yield raw.strip().strip('"').strip("'")
                break
            # JSON: "apiKey": "value"
            json_key = f'"{name}"'
            if stripped.startswith(json_key):
                _, _, raw = stripped.partition(":")
                yield raw.strip().strip('"').strip("'")
                break


def _assert_ai_gateway_url_and_api_key(text: str, ai_namespace: str, config_name: str) -> None:
    """Require RHCL front-door host and a non-EMPTY IDE API key field."""
    host = _ai_gateway_host(ai_namespace)
    assert host in text, (
        f"{config_name} must reference RHCL gateway host {host} "
        f"(escape hatch / guardrails configs are out of scope for ai_gateway):\n"
        f"{text[:500]}"
    )
    values = list(_iter_api_key_field_values(text))
    assert values, (
        f"{config_name} has no API key field "
        f"({', '.join(_API_KEY_FIELD_NAMES)}) while pointing at RHCL"
    )
    for value in values:
        assert value, f"{config_name} has empty API key field"
        assert value != "EMPTY", (
            f"{config_name} uses literal EMPTY placeholder for API key"
        )


def test_continue_config_ai_gateway_api_key(
    require_dev_namespace: str, ai_namespace: str
) -> None:
    ns = require_dev_namespace
    assert oc.resource_exists(
        "configmap", "continue-config", namespace=ns
    ), f"continue-config missing in {ns}"
    yaml_text = oc.configmap_data("continue-config", ns).get("config.yaml") or ""
    _assert_ai_gateway_url_and_api_key(yaml_text, ai_namespace, "continue-config")


def test_roo_code_config_ai_gateway_api_key(
    require_dev_namespace: str, ai_namespace: str
) -> None:
    ns = require_dev_namespace
    assert oc.resource_exists(
        "configmap", "roo-code-provider-config", namespace=ns
    ), f"roo-code-provider-config missing in {ns}"
    joined = "\n".join(oc.configmap_data("roo-code-provider-config", ns).values())
    _assert_ai_gateway_url_and_api_key(
        joined, ai_namespace, "roo-code-provider-config"
    )


def test_cline_config_ai_gateway_api_key(
    require_dev_namespace: str, ai_namespace: str
) -> None:
    ns = require_dev_namespace
    if not oc.resource_exists("configmap", "cline-provider-config", namespace=ns):
        pytest.skip(f"cline-provider-config missing in {ns}")
    joined = "\n".join(oc.configmap_data("cline-provider-config", ns).values())
    _assert_ai_gateway_url_and_api_key(
        joined, ai_namespace, "cline-provider-config"
    )


def test_ide_harness_chat_via_ai_gateway(
    require_dev_namespace: str,
    ai_namespace: str,
    ai_gateway_v1: str,
    model_id: str,
) -> None:
    """E2E: IDE-style chat with attribution headers through the AI Gateway."""
    ns = require_dev_namespace
    api_key = oc.secret_data(
        urls.AI_GATEWAY_APIKEY_SECRET, urls.AI_GATEWAY_APIKEY_KEY, ns
    )
    status, body = oc.in_cluster_http(
        ai_namespace,
        f"{ai_gateway_v1}/chat/completions",
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
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
    assert status == 200, f"IDE harness chat returned {status}: {body!r}"
    assert isinstance(body, dict), body
    choices = body.get("choices") or []
    assert choices, body
    content = oc.message_text(choices[0])
    assert str(content).strip(), f"empty IDE harness response: {body}"


def test_opencode_devworkspace_ai_gateway_api_key(
    require_opencode: dict,
    require_dev_namespace: str,
    ai_namespace: str,
) -> None:
    """OpenCode DevWorkspace must point at RHCL with a non-EMPTY OPENAI_API_KEY."""
    ns = require_dev_namespace
    env = oc.devworkspace_env(require_opencode)
    base_url = env.get("OPENAI_BASE_URL") or env.get("VLLM_ENDPOINT") or ""
    api_key = env.get("OPENAI_API_KEY") or ""
    host = _ai_gateway_host(ai_namespace)
    assert host in base_url, (
        f"OpenCode DevWorkspace must use RHCL gateway host {host}, "
        f"got OPENAI_BASE_URL/VLLM_ENDPOINT={base_url!r}"
    )
    assert api_key.strip(), "OpenCode OPENAI_API_KEY is empty"
    assert api_key != "EMPTY", (
        "OpenCode OPENAI_API_KEY is still the EMPTY placeholder"
    )
    assert oc.resource_exists(
        "secret", urls.AI_GATEWAY_APIKEY_SECRET, namespace=ns
    ), f"secret/{urls.AI_GATEWAY_APIKEY_SECRET} missing in {ns}"
    secret_key = oc.secret_data(
        urls.AI_GATEWAY_APIKEY_SECRET, urls.AI_GATEWAY_APIKEY_KEY, ns
    )
    assert api_key == secret_key, (
        "OpenCode OPENAI_API_KEY does not match pca-ai-gw-apikey Secret"
    )


def test_opencode_chat_completions_with_api_key(
    require_opencode: dict,
    require_dev_namespace: str,
    ai_namespace: str,
    ai_gateway_v1: str,
    model_id: str,
) -> None:
    """OpenCode path: Secret key → Bearer → chat/completions → 200 + reply."""
    del require_opencode  # presence gated by fixture
    ns = require_dev_namespace
    api_key = oc.secret_data(
        urls.AI_GATEWAY_APIKEY_SECRET, urls.AI_GATEWAY_APIKEY_KEY, ns
    )
    status, body = oc.in_cluster_http(
        ai_namespace,
        f"{ai_gateway_v1}/chat/completions",
        method="POST",
        headers={"Authorization": f"Bearer {api_key}"},
        json_body={
            "model": model_id,
            "messages": [{"role": "user", "content": "Reply with the single word pong."}],
            "stream": False,
            "max_tokens": 32,
        },
        timeout_secs=180,
    )
    assert status == 200, f"OpenCode chat/completions returned {status}: {body!r}"
    assert isinstance(body, dict), body
    choices = body.get("choices") or []
    assert choices, body
    content = oc.message_text(choices[0])
    assert str(content).strip(), f"empty OpenCode chat response: {body}"
