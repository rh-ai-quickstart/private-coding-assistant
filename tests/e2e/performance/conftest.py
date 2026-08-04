"""Fixtures for PCA performance ladder tests."""

from __future__ import annotations

import os

import pytest

from pca_e2e import oc
from pca_perf import config as perf_config
from pca_perf.metrics import StageResult, format_report
from pca_perf.users import api_key_for_namespace, require_opencode_users


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "performance: scalability / load ladder (gateway + OpenCode)"
    )


@pytest.fixture(scope="session")
def oc_user() -> str:
    try:
        return oc.whoami()
    except oc.OcError as exc:
        pytest.exit(f"oc whoami failed — log in to the cluster first: {exc}", returncode=1)


@pytest.fixture(scope="session")
def n_list(oc_user: str) -> list[int]:
    del oc_user
    try:
        return perf_config.parse_n_list()
    except ValueError as exc:
        pytest.exit(str(exc), returncode=1)


@pytest.fixture(scope="session")
def ai_ns(oc_user: str) -> str:
    del oc_user
    ns = perf_config.ai_namespace()
    if not oc.resource_exists("gateway", perf_config.AI_GATEWAY_NAME, namespace=ns):
        pytest.fail(
            f"Gateway/{perf_config.AI_GATEWAY_NAME} not found in {ns}. "
            "Deploy AI serving (pca-ai-gateway) before make performance."
        )
    return ns


@pytest.fixture(scope="session")
def model_id(ai_ns: str) -> str:
    env = os.environ.get("MODEL_ID", "").strip()
    if env:
        return env
    if oc.resource_exists(
        "llminferenceservice", perf_config.LLMIS_NAME, namespace=ai_ns
    ):
        name = oc.get_jsonpath(
            "llminferenceservice",
            perf_config.LLMIS_NAME,
            "{.spec.model.name}",
            namespace=ai_ns,
        )
        if name:
            return name
    return perf_config.DEFAULT_MODEL_ID


@pytest.fixture(scope="session")
def perf_namespaces(n_list: list[int]) -> list[str]:
    max_n = max(n_list)
    try:
        return require_opencode_users(max_n)
    except oc.OcError as exc:
        pytest.fail(str(exc))


@pytest.fixture(scope="session")
def gateway_api_key(perf_namespaces: list[str]) -> str:
    return api_key_for_namespace(perf_namespaces[0])


@pytest.fixture(scope="session")
def results_sink() -> list[StageResult]:
    return []


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "perf_n" in metafunc.fixturenames:
        metafunc.parametrize(
            "perf_n", perf_config.parse_n_list(), ids=lambda n: f"N={n}"
        )


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    del exitstatus
    sink = getattr(session.config, "_pca_perf_results", None)
    if sink:
        print("\n" + format_report(sink) + "\n")


@pytest.fixture(scope="session", autouse=True)
def _stash_results(
    results_sink: list[StageResult], request: pytest.FixtureRequest
) -> None:
    request.config._pca_perf_results = results_sink  # type: ignore[attr-defined]
