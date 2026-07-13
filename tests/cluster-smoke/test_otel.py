"""OTel Collector smoke tests (skipped when Langfuse/OTel off)."""

from __future__ import annotations

import pytest

from pca_smoke import oc, urls

pytestmark = pytest.mark.otel


@pytest.fixture(autouse=True)
def _require(require_otel) -> None:
    require_otel()


def test_otel_deploy_available(ai_namespace: str) -> None:
    assert oc.deployment_available(
        urls.OTEL_NAME, ai_namespace
    ), f"deploy/{urls.OTEL_NAME} not Available"


def test_otel_health(ai_namespace: str) -> None:
    # Health extension is on container port 13133 but not exposed via the Service.
    pod_name = oc.run_oc(
        "get",
        "pod",
        "-n",
        ai_namespace,
        "-l",
        "app.kubernetes.io/name=pca-otel-collector",
        "-o",
        "jsonpath={.items[0].metadata.name}",
    ).stdout.strip()
    assert pod_name, "no pca-otel-collector pod"
    pod_ip = oc.get_jsonpath("pod", pod_name, "{.status.podIP}", namespace=ai_namespace)
    assert pod_ip, f"no pod IP for {pod_name}"
    status, body = oc.in_cluster_http(
        ai_namespace,
        f"http://{pod_ip}:13133/",
        insecure=False,
        timeout_secs=30,
    )
    assert status == 200, f"OTel health returned {status}: {body!r}"
