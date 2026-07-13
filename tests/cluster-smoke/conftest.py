"""Pytest fixtures for PCA cluster smoke tests."""

from __future__ import annotations

import os

import pytest

from pca_smoke import oc, urls


def pytest_configure(config: pytest.Config) -> None:
    # Markers are declared in pyproject.toml; ensure oc is usable early.
    pass


@pytest.fixture(scope="session")
def ai_namespace() -> str:
    return os.environ.get("AI_NAMESPACE", "private-assistant-ai-serving")


@pytest.fixture(scope="session")
def dev_namespace() -> str | None:
    value = os.environ.get("DEV_NAMESPACE", "").strip()
    return value or None


@pytest.fixture(scope="session")
def oc_user() -> str:
    try:
        return oc.whoami()
    except oc.OcError as exc:
        pytest.exit(f"oc whoami failed — log in to the cluster first: {exc}", returncode=1)


@pytest.fixture(scope="session")
def model_id(ai_namespace: str, oc_user: str) -> str:
    del oc_user  # ensure login check runs
    if not oc.resource_exists("llminferenceservice", urls.LLMIS_NAME, namespace=ai_namespace):
        return urls.DEFAULT_MODEL_ID
    name = oc.get_jsonpath(
        "llminferenceservice",
        urls.LLMIS_NAME,
        "{.spec.model.name}",
        namespace=ai_namespace,
    )
    return name or urls.DEFAULT_MODEL_ID


@pytest.fixture(scope="session")
def gateway_v1(ai_namespace: str) -> str:
    return urls.gateway_v1(ai_namespace)


def require_resource(resource: str, name: str, namespace: str, reason: str) -> None:
    if not oc.resource_exists(resource, name, namespace=namespace):
        pytest.skip(reason)


@pytest.fixture
def require_langfuse(ai_namespace: str):
    def _check() -> None:
        require_resource(
            "route",
            urls.LANGFUSE_ROUTE,
            ai_namespace,
            "Langfuse not deployed (no pca-langfuse route)",
        )

    return _check


@pytest.fixture
def require_otel(ai_namespace: str):
    def _check() -> None:
        require_resource(
            "deploy",
            urls.OTEL_NAME,
            ai_namespace,
            "OTel Collector not deployed",
        )

    return _check


@pytest.fixture
def require_guardrails(ai_namespace: str):
    def _check() -> None:
        require_resource(
            "svc",
            urls.GUARDRAILS_PROXY,
            ai_namespace,
            "Guardrails proxy not deployed",
        )

    return _check


@pytest.fixture
def require_dev_namespace(dev_namespace: str | None) -> str:
    if not dev_namespace:
        pytest.skip("DEV_NAMESPACE not set — skipping DevSpaces tests")
    return dev_namespace
