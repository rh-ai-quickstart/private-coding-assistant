"""Pytest fixtures for PCA cluster e2e tests."""

from __future__ import annotations

import os
import time

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


@pytest.fixture
def opencode_workspace(require_dev_namespace: str) -> tuple[str, str]:
    ns = require_dev_namespace
    dw = oc.find_opencode_devworkspace(ns)
    assert dw is not None, (
        f"no OpenCode DevWorkspace in {ns}. OpenCode must be deployed "
        "(make e2e assumes TYPE=opencode / OpenCode DW present)"
    )
    name = (dw.get("metadata") or {}).get("name") or ""
    assert name, "DevWorkspace missing metadata.name"
    dw = oc.ensure_devworkspace_started(ns, name, timeout_secs=600)
    deadline = time.time() + 120
    last_err: oc.OcError | None = None
    while time.time() < deadline:
        dw = oc.get_json("devworkspace", name, namespace=ns)
        workspace_id = (dw.get("status") or {}).get("devworkspaceId") or ""
        if workspace_id:
            try:
                return ns, oc.find_workspace_pod(ns, workspace_id)
            except oc.OcError as exc:
                last_err = exc
        time.sleep(3)
    raise AssertionError(
        f"no Running workspace pod in {ns} within 120s ({last_err})"
    )


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
    oc.assert_openai_base_url_reaches_maas(base)
