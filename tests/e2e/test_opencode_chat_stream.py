"""OpenCode chat via MaaS: first assistant text arrives before the turn ends."""

from __future__ import annotations

import pytest

from pca_e2e import oc
from pca_e2e import opencode as ocapi

pytestmark = pytest.mark.opencode

_MAX_PREFILL_SECS = 15.0


def test_opencode_chat_streams_first_token(
    opencode_workspace: tuple[str, str],
) -> None:
    ns, pod = opencode_workspace
    assert oc.resource_exists("secret", "opencode-web-password", namespace=ns), (
        f"secret/opencode-web-password missing in {ns}"
    )
    password = oc.secret_data("opencode-web-password", "password", ns)
    assert password.strip(), "opencode-web-password is empty"

    provider_id, model_id = ocapi.resolve_model_ids(ns, pod)
    with oc.PortForward(ns, pod, 4096) as pf:
        with ocapi.OpenCodeClient(pf.base_url, password, timeout_secs=180) as client:
            client.health()
            session = client.create_session("pca-e2e-chat-stream")
            sid = session["id"]
            resp, _gen, _gs, _ge, prefill_secs, _decode = (
                client.run_turn_with_generation_timing(
                    sid,
                    "Reply with the single word pong and nothing else.",
                    provider_id=provider_id,
                    model_id=model_id,
                    timeout=180,
                )
            )
            text = ocapi.message_text(resp)
            assert text.strip(), f"empty OpenCode assistant text: {resp!r}"
            assert prefill_secs < _MAX_PREFILL_SECS, (
                f"OpenCode first text took {prefill_secs:.2f}s "
                f"(max {_MAX_PREFILL_SECS})"
            )
