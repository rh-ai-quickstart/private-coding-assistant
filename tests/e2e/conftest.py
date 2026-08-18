"""Pytest fixtures for PCA cluster e2e tests."""

from __future__ import annotations

import os

import pytest

from pca_e2e import oc


@pytest.fixture(scope="session")
def oc_user() -> str:
    try:
        return oc.whoami()
    except oc.OcError as exc:
        pytest.exit(f"oc whoami failed — log in to the cluster first: {exc}", returncode=1)


@pytest.fixture(scope="session")
def dev_namespace(oc_user: str) -> str:
    del oc_user
    value = os.environ.get("DEV_NAMESPACE", "").strip()
    if not value:
        pytest.skip("DEV_NAMESPACE not set — pass DEV_USER= to make e2e")
    return value


@pytest.fixture(scope="session")
def require_dev_namespace(dev_namespace: str) -> str:
    return dev_namespace


@pytest.fixture(scope="session")
def ai_namespace() -> str:
    return os.environ.get("AI_NAMESPACE", "private-assistant-ai-serving").strip()


@pytest.fixture(scope="session")
def require_guardrails_proxy(ai_namespace: str) -> str:
    if not oc.resource_exists("svc", "guardrails-proxy", namespace=ai_namespace):
        pytest.exit(
            f"guardrails-proxy Service missing in {ai_namespace} — "
            "deploy with guardrails.enabled=true",
            returncode=1,
        )
    return ai_namespace


@pytest.fixture(scope="session")
def require_opencode_guardrails_url(
    require_dev_namespace: str,
    ai_namespace: str,
) -> None:
    dw = oc.find_opencode_devworkspace(require_dev_namespace)
    assert dw is not None, f"no OpenCode DevWorkspace in {require_dev_namespace}"
    base = oc.devworkspace_env(dw).get("OPENAI_BASE_URL", "")
    host = f"pca-ai-gateway-data-science-gateway-class.{ai_namespace}"
    assert host in base, (
        f"OPENAI_BASE_URL must route through pca-ai-gateway ({host}), got {base!r}. "
        "Redeploy pca-devspaces so chat uses the RHCL gateway (guardrails is an HTTPRoute backend)."
    )
