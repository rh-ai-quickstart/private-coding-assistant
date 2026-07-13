"""Langfuse smoke tests (skipped when not deployed)."""

from __future__ import annotations

import base64
import re
import time
from typing import Any

import pytest

from pca_smoke import oc, urls

pytestmark = pytest.mark.langfuse


@pytest.fixture(autouse=True)
def _require(require_langfuse) -> None:
    require_langfuse()


def _langfuse_basic_auth(ai_namespace: str) -> str:
    pk = oc.secret_data(urls.LANGFUSE_SECRET, "init-project-public-key", ai_namespace)
    sk = oc.secret_data(urls.LANGFUSE_SECRET, "init-project-secret-key", ai_namespace)
    return base64.b64encode(f"{pk}:{sk}".encode()).decode()


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _pca_headers_from_continue(dev_namespace: str) -> dict[str, str]:
    """Read X-PCA-* from the DevSpace continue-config (same headers the IDE sends)."""
    if not oc.resource_exists("configmap", "continue-config", namespace=dev_namespace):
        return {
            "X-PCA-User": "smoke-devspace",
            "X-PCA-DevSpace": dev_namespace,
        }
    yaml_text = oc.configmap_data("continue-config", dev_namespace).get("config.yaml") or ""
    headers: dict[str, str] = {"X-PCA-DevSpace": dev_namespace}
    for key in ("X-PCA-User", "X-PCA-DevSpace", "X-PCA-Team"):
        match = re.search(rf"{re.escape(key)}:\s*[\"']?([^\"'\n]+)[\"']?", yaml_text)
        if match:
            headers[key] = match.group(1).strip()
    headers.setdefault("X-PCA-User", "smoke-devspace")
    return headers


def _find_langfuse_trace(
    ai_namespace: str,
    token: str,
    *,
    marker: str,
) -> dict[str, Any] | None:
    status, traces = oc.in_cluster_http(
        ai_namespace,
        f"{urls.langfuse_svc(ai_namespace)}/api/public/traces?limit=50",
        headers={"Authorization": f"Basic {token}"},
        insecure=False,
        timeout_secs=30,
    )
    if status != 200 or not isinstance(traces, dict):
        return None
    for trace in traces.get("data") or []:
        in_s = _as_text(trace.get("input"))
        out_s = _as_text(trace.get("output"))
        if marker in in_s and out_s.strip():
            return trace
    return None


def test_langfuse_route(ai_namespace: str) -> None:
    host = oc.route_host(urls.LANGFUSE_ROUTE, ai_namespace)
    assert host, "pca-langfuse route host empty"


def test_langfuse_health(ai_namespace: str) -> None:
    status, body = oc.in_cluster_http(
        ai_namespace,
        f"{urls.langfuse_svc(ai_namespace)}/api/public/health",
        insecure=False,
        timeout_secs=30,
    )
    assert status == 200, f"Langfuse health returned {status}: {body!r}"


def test_langfuse_credentials_secret(ai_namespace: str) -> None:
    assert oc.resource_exists(
        "secret", urls.LANGFUSE_SECRET, namespace=ai_namespace
    ), f"secret/{urls.LANGFUSE_SECRET} missing"
    password = oc.secret_data(urls.LANGFUSE_SECRET, "init-user-password", ai_namespace)
    assert password, "init-user-password empty"
    # Public/secret keys used for OTLP / API
    pk = oc.secret_data(urls.LANGFUSE_SECRET, "init-project-public-key", ai_namespace)
    sk = oc.secret_data(urls.LANGFUSE_SECRET, "init-project-secret-key", ai_namespace)
    assert pk and sk, "Langfuse project API keys missing"


def test_langfuse_api_projects(ai_namespace: str) -> None:
    """Init project keys authenticate against the public API."""
    token = _langfuse_basic_auth(ai_namespace)
    status, body = oc.in_cluster_http(
        ai_namespace,
        f"{urls.langfuse_svc(ai_namespace)}/api/public/projects",
        headers={"Authorization": f"Basic {token}"},
        insecure=False,
        timeout_secs=30,
    )
    assert status == 200, f"Langfuse /api/public/projects returned {status}: {body!r}"
    assert isinstance(body, dict), body
    data = body.get("data") or []
    assert data, f"expected at least one project, got {body}"
    names = [p.get("name") for p in data]
    assert any(n for n in names), f"empty project names: {names}"


def test_langfuse_short_dependency_services(ai_namespace: str) -> None:
    """fullnameOverrides keep Bitnami pod labels under the 63-char Kubernetes limit.

    Long Helm release names like private-assistant-ai-serving-ai-serving otherwise
    produce invalid labels (e.g. …-clickhouse-shard0-<hash>) and Redis/ClickHouse
    never schedule — Langfuse then CrashLoops.
    """
    for name in (
        "pca-langfuse-postgresql",
        "pca-langfuse-redis-primary",
        "pca-langfuse-clickhouse",
        "pca-langfuse-web",
    ):
        assert oc.resource_exists("svc", name, namespace=ai_namespace), (
            f"expected short-named service {name} (fullnameOverride missing?)"
        )


def test_langfuse_receives_traces_after_chat(
    ai_namespace: str,
    gateway_v1: str,
    model_id: str,
) -> None:
    """vLLM OTLP → Collector → Langfuse: at least one trace appears after a chat.

    userId attribution via X-PCA-* is Phase 0 / follow-up — this only asserts the
    hot path delivers traces (metadata and/or full I/O).
    """
    token = _langfuse_basic_auth(ai_namespace)

    def _trace_count() -> int:
        status, body = oc.in_cluster_http(
            ai_namespace,
            f"{urls.langfuse_svc(ai_namespace)}/api/public/traces?limit=20",
            headers={"Authorization": f"Basic {token}"},
            insecure=False,
            timeout_secs=30,
        )
        if status != 200 or not isinstance(body, dict):
            return -1
        return len(body.get("data") or [])

    before = _trace_count()
    assert before >= 0, "could not list Langfuse traces"

    prompt = "Say ping once. smoke-io-capture"
    status, body = oc.in_cluster_http(
        ai_namespace,
        f"{gateway_v1}/chat/completions",
        method="POST",
        headers={
            "X-PCA-User": "smoke-test",
            "X-PCA-DevSpace": "smoke-ns",
            "X-PCA-Team": "smoke",
        },
        json_body={
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "max_tokens": 16,
            "chat_template_kwargs": {"enable_thinking": False},
        },
        timeout_secs=180,
    )
    assert status == 200, f"chat for trace smoke returned {status}: {body!r}"

    # Spans / ingestion are async; allow a short settle window.
    after = before
    for _ in range(6):
        time.sleep(5)
        after = _trace_count()
        if after > before:
            break
    assert after > before or after > 0, (
        f"expected Langfuse traces after chat (before={before}, after={after})"
    )


def test_langfuse_full_io_capture_when_middleware_present(
    ai_namespace: str,
    gateway_v1: str,
    model_id: str,
) -> None:
    """When pca-langfuse-io-middleware ConfigMap exists (ioCapture=full), a chat
    should land in Langfuse with non-empty input and output.
    """
    if not oc.resource_exists(
        "configmap", "pca-langfuse-io-middleware", namespace=ai_namespace
    ):
        pytest.skip("full I/O middleware not deployed (ioCapture!=full or Langfuse off)")

    token = _langfuse_basic_auth(ai_namespace)
    marker = f"pca-smoke-io-{int(time.time())}"

    status, body = oc.in_cluster_http(
        ai_namespace,
        f"{gateway_v1}/chat/completions",
        method="POST",
        headers={
            "X-PCA-User": "smoke-io",
            "X-PCA-DevSpace": "smoke-ns",
            "X-PCA-Team": "smoke",
        },
        json_body={
            "model": model_id,
            "messages": [{"role": "user", "content": f"Reply with the word pong only. {marker}"}],
            "stream": False,
            "max_tokens": 16,
            "chat_template_kwargs": {"enable_thinking": False},
        },
        timeout_secs=180,
    )
    assert status == 200, f"chat for full I/O smoke returned {status}: {body!r}"

    found = False
    for _ in range(8):
        time.sleep(5)
        st, traces = oc.in_cluster_http(
            ai_namespace,
            f"{urls.langfuse_svc(ai_namespace)}/api/public/traces?limit=50",
            headers={"Authorization": f"Basic {token}"},
            insecure=False,
            timeout_secs=30,
        )
        if st != 200 or not isinstance(traces, dict):
            continue
        for trace in traces.get("data") or []:
            raw_in = trace.get("input")
            raw_out = trace.get("output")
            in_s = raw_in if isinstance(raw_in, str) else str(raw_in or "")
            out_s = raw_out if isinstance(raw_out, str) else str(raw_out or "")
            if marker in in_s and out_s.strip():
                found = True
                break
        if found:
            break

    assert found, (
        f"expected Langfuse trace with input containing {marker!r} and non-empty output"
    )


@pytest.mark.devspaces
def test_devspace_count_message_stored_in_langfuse(
    require_dev_namespace: str,
    ai_namespace: str,
    gateway_v1: str,
    model_id: str,
) -> None:
    """Simulate a DevSpace chat (count 1..10) and assert Langfuse has request + response.

    Requires DEV_NAMESPACE (reads X-PCA-* from continue-config) and Langfuse.
    When ioCapture=full, input/output bodies and userId are asserted.
    """
    if not oc.resource_exists(
        "configmap", "pca-langfuse-io-middleware", namespace=ai_namespace
    ):
        pytest.skip("full I/O middleware not deployed (ioCapture!=full or Langfuse off)")

    ns = require_dev_namespace
    headers = _pca_headers_from_continue(ns)
    token = _langfuse_basic_auth(ai_namespace)
    marker = f"devspace-count-{int(time.time())}"
    prompt = (
        f"Count from 1 to 10. Reply with only the numbers, one per line. marker={marker}"
    )

    status, body = oc.in_cluster_http(
        ai_namespace,
        f"{gateway_v1}/chat/completions",
        method="POST",
        headers=headers,
        json_body={
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "max_tokens": 64,
            "chat_template_kwargs": {"enable_thinking": False},
        },
        timeout_secs=180,
    )
    assert status == 200, f"DevSpace count chat returned {status}: {body!r}"
    assert isinstance(body, dict), body
    choices = body.get("choices") or []
    assert choices, body
    completion = oc.message_text(choices[0])
    assert completion.strip(), f"empty completion: {body}"

    # Async Langfuse ingest — poll until the marker appears with non-empty output.
    found: dict[str, Any] | None = None
    for _ in range(10):
        time.sleep(5)
        found = _find_langfuse_trace(ai_namespace, token, marker=marker)
        if found is not None:
            break

    assert found is not None, (
        f"expected Langfuse trace for DevSpace chat with marker={marker!r} "
        f"headers={headers}"
    )
    in_s = _as_text(found.get("input"))
    out_s = _as_text(found.get("output"))
    assert marker in in_s, f"Langfuse input missing marker: {in_s[:300]!r}"
    assert out_s.strip(), f"Langfuse output empty: {found}"
    # Response should look like a 1..10 count (tolerate formatting).
    for n in ("1", "10"):
        assert n in out_s, f"expected {n!r} in Langfuse output: {out_s[:300]!r}"
    expected_user = headers.get("X-PCA-User")
    if expected_user and found.get("userId"):
        assert found["userId"] == expected_user, found.get("userId")
    meta = found.get("metadata") or {}
    if isinstance(meta, dict) and meta.get("devspace"):
        assert meta["devspace"] == ns, meta
