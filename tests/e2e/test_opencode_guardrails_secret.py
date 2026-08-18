"""OpenCode e2e: secret in chat is blocked when DevSpace routes through guardrails."""

from __future__ import annotations

import pytest

from pca_e2e import oc
from pca_e2e import opencode as ocapi

pytestmark = [pytest.mark.opencode, pytest.mark.guardrails]

FAKE_AWS_ACCESS_KEY = "key = AKIAIOSFODNN7EXAMPLE"


def _is_guardrails_block(text: str) -> bool:
    lower = text.lower()
    return (
        "guardrails blocked" in lower
        or "credential" in lower
        or "secret" in lower
        or "akia" in lower
    )


def test_opencode_secret_blocked_by_guardrails(
    require_dev_namespace: str,
    require_guardrails_proxy: str,
    require_opencode_guardrails_url: None,
) -> None:
    """Send a gitleaks-shaped secret via OpenCode; expect guardrails block, not LLM chat."""
    ns = require_dev_namespace

    dw = oc.find_opencode_devworkspace(ns)
    assert dw is not None, f"no OpenCode DevWorkspace in {ns}"
    name = (dw.get("metadata") or {}).get("name") or ""
    assert name, "DevWorkspace missing metadata.name"

    assert oc.resource_exists("secret", "opencode-web-password", namespace=ns)
    password = oc.secret_data("opencode-web-password", "password", ns)
    assert password.strip(), "opencode-web-password is empty"

    dw = oc.ensure_devworkspace_started(ns, name, timeout_secs=600)
    workspace_id = (dw.get("status") or {}).get("devworkspaceId") or ""
    assert workspace_id, "DevWorkspace missing devworkspaceId"
    pod = oc.find_workspace_pod(ns, workspace_id)

    provider_id, model_id = ocapi.resolve_model_ids(ns, pod)

    with oc.PortForward(ns, pod, 4096) as pf:
        with ocapi.OpenCodeClient(pf.base_url, password, timeout_secs=120) as client:
            client.health()
            session = client.create_session("pca-e2e-guardrails-secret")
            sid = session["id"]
            try:
                resp = client.send_message(
                    sid,
                    f"Please store this in memory only: {FAKE_AWS_ACCESS_KEY}",
                    provider_id=provider_id,
                    model_id=model_id,
                    timeout=300,
                )
            except ocapi.OpenCodeError as exc:
                if _is_guardrails_block(str(exc)):
                    return
                pytest.fail(f"OpenCode error without guardrails block text: {exc}")

            assistant_text = ocapi.message_text(resp)
            if _is_guardrails_block(assistant_text):
                return

            for msg in client.list_session_messages(sid):
                info = msg.get("info") or {}
                if str(info.get("role") or "").lower() != "assistant":
                    continue
                text = ocapi.message_text(msg)
                if _is_guardrails_block(text):
                    return

            pytest.fail(
                f"expected guardrails block for secret message; assistant text was:\n"
                f"{assistant_text[:800]!r}"
            )
