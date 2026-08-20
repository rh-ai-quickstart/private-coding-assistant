"""Unit tests for MaaS e2e helpers (no cluster)."""

from __future__ import annotations

import shlex
import sys
from dataclasses import replace
from pathlib import Path

import pytest

_E2E = Path(__file__).resolve().parents[1] / "e2e"
if str(_E2E) not in sys.path:
    sys.path.insert(0, str(_E2E))

from pca_e2e import oc
from pca_e2e import routes

CLUSTERIP = (
    "https://maas-default-gateway-data-science-gateway-class."
    "openshift-ingress.svc.cluster.local/v1"
)


def test_is_maas_openai_base_url_accepts_clusterip_and_apps_host() -> None:
    assert oc.is_maas_openai_base_url(CLUSTERIP)
    assert oc.is_maas_openai_base_url("https://maas.apps.example.com/v1")
    assert oc.is_maas_openai_base_url("https://maas-default-gateway/v1")


def test_is_maas_openai_base_url_rejects_typosquat_and_legacy() -> None:
    assert not oc.is_maas_openai_base_url("https://notmaas.apps.example.com/v1")
    assert not oc.is_maas_openai_base_url(
        "https://pca-ai-gateway-data-science-gateway-class."
        "ai-serving.svc.cluster.local/v1"
    )
    assert not oc.is_maas_openai_base_url(
        "https://llm-d-gateway-data-science-gateway-class."
        "ai-serving.svc.cluster.local/v1"
    )
    assert not oc.is_maas_openai_base_url(
        "https://example.com/v1?next=maas-default-gateway"
    )
    assert not oc.is_maas_openai_base_url("")


def test_is_maas_openai_base_url_accepts_pca_maas_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PCA_MAAS_HOSTNAME", "ai.corp.example.com")
    assert oc.is_maas_openai_base_url("https://ai.corp.example.com/v1")
    assert not oc.is_maas_openai_base_url("https://other.corp.example.com/v1")
    monkeypatch.setenv("PCA_MAAS_HOSTNAME", "https://ai.corp.example.com:443")
    assert oc.is_maas_openai_base_url("https://ai.corp.example.com/v1")


def test_origin_from_base_url_strips_v1_and_trailing_slashes() -> None:
    assert routes.origin_from_base_url("https://maas.apps.example.com/v1") == (
        "https://maas.apps.example.com"
    )
    assert routes.origin_from_base_url("https://h/v1///") == "https://h"
    assert routes.origin_from_base_url("https://h") == "https://h"


def test_workspace_curl_script_strips_trailing_slashes_like_origin_helper() -> None:
    script = oc.workspace_curl_script(
        path="/v1/models", method="GET", body_b64="", timeout=10
    )
    assert 'while [[ "$base" == */ ]]; do' in script
    assert 'origin="${base%/v1}"' in script


def test_json_body_for_disables_thinking_on_chat_payloads() -> None:
    case = next(c for c in routes.ROUTE_CASES if c.id == "tab-local-secret")
    body = routes.json_body_for(case, "Qwen/test")
    assert body is not None
    assert body["chat_template_kwargs"]["enable_thinking"] is False
    assert body["model"] == "Qwen/test"
    assert case.path.startswith("/local/v1")


def test_json_body_for_none_payload_has_no_body() -> None:
    case = next(c for c in routes.ROUTE_CASES if c.payload == "none")
    assert routes.json_body_for(case, "Qwen/test") is None


def test_json_body_for_rejects_unknown_payload() -> None:
    case = next(c for c in routes.ROUTE_CASES if c.payload == "pong")
    bogus = replace(case, payload="nope")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unknown payload"):
        routes.json_body_for(bogus, "m")


def test_route_class_paths_and_skips_match_table() -> None:
    by_id = {c.id: c for c in routes.ROUTE_CASES}
    for case in routes.ROUTE_CASES:
        if case.route_class == "chat-guarded":
            assert case.path == "/v1/chat/completions"
        elif case.route_class == "tab-local":
            assert case.path.startswith("/local/v1")
        elif case.route_class == "passthrough":
            assert case.path.startswith("/v1/models")
        else:
            raise AssertionError(case.route_class)
        if case.expect_blocked is True:
            assert case.payload == "secret"
            assert case.skip_if is routes.skip_unless_guardrails
    assert by_id["tab-local-secret"].skip_if is routes.skip_unless_guardrails
    assert by_id["sr-off-chat-still-local"].skip_if is (
        routes.skip_if_semantic_router_present
    )
    assert by_id["chat-guarded-secret-stream"].stream is True


def test_workspace_curl_script_quotes_path_metacharacters() -> None:
    nasty = "/v1/foo$(touch /tmp/pwned)"
    script = oc.workspace_curl_script(
        path=nasty, method="GET", body_b64="", timeout=10
    )
    quoted = shlex.quote(nasty)
    assert f'url="${{origin}}"{quoted}' in script
    assert f'url="${{origin}}{nasty}"' not in script


def test_workspace_curl_script_rejects_relative_path() -> None:
    with pytest.raises(oc.OcError, match="absolute path"):
        oc.workspace_curl_script(
            path="v1/chat", method="GET", body_b64="", timeout=10
        )


def test_workspace_curl_script_uses_mktemp() -> None:
    script = oc.workspace_curl_script(
        path="/v1/models", method="GET", body_b64="", timeout=10
    )
    assert "mktemp /tmp/pca-e2e-body.XXXXXX" in script
    assert "mktemp /tmp/pca-e2e-req.XXXXXX" in script


def test_parse_workspace_curl_output_happy_path() -> None:
    text = "200 0.12 1.50\n---PCA_E2E_BODY---\n{\"id\":1}"
    parsed = oc.parse_workspace_curl_output(text)
    assert parsed["status"] == 200
    assert parsed["ttfb"] == 0.12
    assert parsed["total"] == 1.5
    assert parsed["body"] == '{"id":1}'


def test_parse_workspace_curl_output_keeps_marker_inside_body() -> None:
    text = (
        "200 0.1 0.2\n---PCA_E2E_BODY---\n"
        "prefix---PCA_E2E_BODY---\nactual"
    )
    parsed = oc.parse_workspace_curl_output(text)
    assert parsed["body"] == "prefix---PCA_E2E_BODY---\nactual"


def test_parse_workspace_curl_output_missing_marker() -> None:
    with pytest.raises(oc.OcError, match="missing body marker"):
        oc.parse_workspace_curl_output("200 0.1 0.2\nnope")


def test_parse_workspace_curl_output_bad_metrics() -> None:
    with pytest.raises(oc.OcError, match="bad metrics"):
        oc.parse_workspace_curl_output("200 onlytwo\n---PCA_E2E_BODY---\n")
    with pytest.raises(oc.OcError, match="bad metrics"):
        oc.parse_workspace_curl_output("xx 0.1 0.2\n---PCA_E2E_BODY---\n")
