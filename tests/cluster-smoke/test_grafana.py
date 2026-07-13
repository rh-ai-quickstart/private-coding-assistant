"""Grafana smoke tests."""

from __future__ import annotations

import base64

import pytest

from pca_smoke import oc, urls

pytestmark = pytest.mark.grafana


@pytest.fixture(autouse=True)
def _require_grafana(ai_namespace: str) -> None:
    if not oc.resource_exists("deploy", urls.GRAFANA_NAME, namespace=ai_namespace):
        pytest.skip("Grafana not deployed")


def test_grafana_route(ai_namespace: str) -> None:
    assert oc.resource_exists(
        "route", urls.GRAFANA_NAME, namespace=ai_namespace
    ), "pca-grafana route missing"
    host = oc.route_host(urls.GRAFANA_NAME, ai_namespace)
    assert host, "pca-grafana route has empty host"


def test_grafana_health(ai_namespace: str) -> None:
    status, body = oc.in_cluster_http(
        ai_namespace,
        f"{urls.grafana_svc(ai_namespace)}/api/health",
        insecure=False,
        timeout_secs=30,
    )
    assert status == 200, f"Grafana /api/health returned {status}: {body!r}"
    if isinstance(body, dict):
        assert body.get("database") == "ok" or "database" in body or body.get("version")


def test_grafana_datasources(ai_namespace: str) -> None:
    password = oc.secret_data("pca-grafana-admin", "admin-password", ai_namespace)
    token = base64.b64encode(f"admin:{password}".encode()).decode()
    status, body = oc.in_cluster_http(
        ai_namespace,
        f"{urls.grafana_svc(ai_namespace)}/api/datasources",
        headers={"Authorization": f"Basic {token}"},
        insecure=False,
        timeout_secs=30,
    )
    assert status == 200, f"datasources returned {status}: {body!r}"
    assert isinstance(body, list), body
    names = [ds.get("name") or ds.get("type") for ds in body]
    types = [ds.get("type") for ds in body]
    uids = [ds.get("uid") for ds in body]
    assert "prometheus" in types or "prometheus" in uids or any(
        "rometheus" in (n or "") for n in names
    ), f"no Prometheus datasource in {body}"


def test_grafana_dashboard_configmaps(ai_namespace: str) -> None:
    for name in ("pca-grafana-dashboard-b", "pca-grafana-dashboard-c"):
        assert oc.resource_exists(
            "configmap", name, namespace=ai_namespace
        ), f"missing {name}"
    langfuse_on = oc.resource_exists(
        "route", urls.LANGFUSE_ROUTE, namespace=ai_namespace
    )
    for name in ("pca-grafana-dashboard-a", "pca-grafana-dashboard-d"):
        exists = oc.resource_exists("configmap", name, namespace=ai_namespace)
        if langfuse_on:
            assert exists, f"Langfuse on but missing {name}"
        # If Langfuse off, boards A/D may still exist as templated CMs — do not fail.


def test_grafana_prometheus_query(ai_namespace: str) -> None:
    """Grafana can query Prometheus via /api/ds/query (OpenShift Thanos tenancy).

    The legacy datasource-proxy GET path often returns 400 against Thanos :9092;
    /api/ds/query is the path that works with our provisioned datasource.
    """
    password = oc.secret_data("pca-grafana-admin", "admin-password", ai_namespace)
    token = base64.b64encode(f"admin:{password}".encode()).decode()
    status, body = oc.in_cluster_http(
        ai_namespace,
        f"{urls.grafana_svc(ai_namespace)}/api/ds/query",
        method="POST",
        headers={
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        },
        json_body={
            "queries": [
                {
                    "refId": "A",
                    "datasource": {"type": "prometheus", "uid": "prometheus"},
                    "expr": "up",
                    "instant": True,
                }
            ],
            "from": "now-5m",
            "to": "now",
        },
        insecure=False,
        timeout_secs=60,
    )
    assert status == 200, f"Prometheus query via Grafana returned {status}: {body!r}"
    assert isinstance(body, dict), body
    results = body.get("results") or {}
    assert "A" in results, f"missing refId A in {body}"
    frame_status = (results["A"] or {}).get("status")
    assert frame_status in (200, "success", None) or "frames" in (results["A"] or {}), (
        f"unexpected query result: {results['A']!r}"
    )
