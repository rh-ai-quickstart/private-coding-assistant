"""MaaS HTTPRoute classes from the DevSpace workspace (user key + URL)."""

from __future__ import annotations

import pytest

from pca_e2e import oc
from pca_e2e import routes

pytestmark = [pytest.mark.opencode, pytest.mark.maas]


@pytest.mark.parametrize("case", routes.ROUTE_CASES, ids=lambda c: c.id)
def test_maas_route_class(
    case: routes.RouteCase,
    opencode_workspace: tuple[str, str],
    ai_namespace: str,
) -> None:
    ns, pod = opencode_workspace
    if case.skip_if:
        reason = case.skip_if(ai_namespace)
        if reason:
            pytest.skip(reason)
    model = routes.model_id_from_pod(ns, pod)
    result = oc.workspace_openai_curl(
        ns,
        pod,
        path=case.path,
        method=case.method,
        json_body=routes.json_body_for(case, model),
        timeout=90,
    )
    assert result["status"] == case.expect_status, result["body"][:800]
    blocked = "guardrails blocked" in result["body"].lower()
    if case.expect_blocked is True:
        assert blocked, result["body"][:800]
    elif case.expect_blocked is False:
        assert not blocked, result["body"][:800]
    if case.max_ttfb_secs is not None:
        assert result["ttfb"] < case.max_ttfb_secs, (
            f"ttfb={result['ttfb']} total={result['total']} "
            f"max={case.max_ttfb_secs}"
        )
