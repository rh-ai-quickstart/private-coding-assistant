from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_SMOKE = Path(__file__).resolve().parents[1] / "cluster-smoke"
if str(_SMOKE) not in sys.path:
    sys.path.insert(0, str(_SMOKE))

from pca_smoke import oc, urls

DEFAULT_FQDN = (
    "maas-default-gateway-data-science-gateway-class."
    "openshift-ingress.svc.cluster.local"
)


@pytest.fixture
def clean_maas_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PCA_MAAS_HOSTNAME", raising=False)
    monkeypatch.delenv("PCA_MAAS_GATEWAY_CLASS", raising=False)


def test_ai_gateway_host_default_is_cluster_fqdn(clean_maas_env: None) -> None:
    host = urls.ai_gateway_host()
    assert host == DEFAULT_FQDN
    assert host.endswith(".svc.cluster.local")
    assert "ai-dev02" not in host
    assert "maas-default-gateway-." not in host


def test_ai_gateway_host_empty_gateway_class_uses_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PCA_MAAS_GATEWAY_CLASS", "")
    monkeypatch.delenv("PCA_MAAS_HOSTNAME", raising=False)
    host = urls.ai_gateway_host()
    assert host == DEFAULT_FQDN
    assert "-." not in host


def test_ai_gateway_host_custom_gateway_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PCA_MAAS_GATEWAY_CLASS", "custom-gw-class")
    monkeypatch.delenv("PCA_MAAS_HOSTNAME", raising=False)
    assert urls.ai_gateway_host() == (
        "maas-default-gateway-custom-gw-class."
        "openshift-ingress.svc.cluster.local"
    )


def test_ai_gateway_host_strips_scheme_and_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PCA_MAAS_HOSTNAME", "https://maas.apps.example.com/v1"
    )
    assert urls.ai_gateway_host() == "maas.apps.example.com"


def test_ai_gateway_host_strips_scheme_and_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PCA_MAAS_HOSTNAME", "https://ai.corp.example.com:443")
    assert urls.ai_gateway_host() == "ai.corp.example.com"


def test_ai_gateway_host_plain_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PCA_MAAS_HOSTNAME", "ai.corp.example.com")
    assert urls.ai_gateway_host() == "ai.corp.example.com"


def test_in_cluster_http_shell_skips_cat_when_body_missing() -> None:
    script = oc.in_cluster_http_shell("https://example.invalid/v1")
    assert "if [ -f" in script
    assert "cat /tmp/body" not in script
    assert re.search(r"/tmp/pca-smoke-[0-9a-f]{12}", script)


def test_in_cluster_http_shell_uses_unique_body_path() -> None:
    a = oc.in_cluster_http_shell("https://example.invalid/a")
    b = oc.in_cluster_http_shell("https://example.invalid/b")
    paths = re.findall(r"/tmp/pca-smoke-[0-9a-f]{12}", a)
    other = re.findall(r"/tmp/pca-smoke-[0-9a-f]{12}", b)
    assert paths and other
    assert paths[0] != other[0]


def test_in_cluster_http_shell_respects_explicit_body_path() -> None:
    script = oc.in_cluster_http_shell(
        "https://example.invalid/v1", body_path="/tmp/pca-smoke-fixed"
    )
    assert "/tmp/pca-smoke-fixed" in script
    assert "if [ -f /tmp/pca-smoke-fixed ]" in script
    assert "cat /tmp/pca-smoke-fixed" in script


def test_parse_in_cluster_http_json_success() -> None:
    stdout = '200\n{"ok": true}\npod "pca-smoke-abc" deleted'
    status, body = oc.parse_in_cluster_http_output(stdout)
    assert status == 200
    assert body == {"ok": True}


def test_parse_in_cluster_http_missing_body_returns_zero_and_stderr() -> None:
    stderr = "curl: (6) Could not resolve host: maas-default-gateway-.openshift-ingress"
    status, body = oc.parse_in_cluster_http_output("000\n", stderr)
    assert status == 0
    assert "Could not resolve host" in str(body)


def test_parse_in_cluster_http_cat_error_in_stderr_only() -> None:
    stderr = "cat: can't open '/tmp/body': No such file or directory"
    status, body = oc.parse_in_cluster_http_output("", stderr)
    assert status == 0
    assert "can't open '/tmp/body'" in str(body)
