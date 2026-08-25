"""Cluster-internal and route URL builders."""

from __future__ import annotations

import os

from pca_smoke.oc import http_hostname as _http_hostname

DEFAULT_MODEL_ID = "Qwen/Qwen3.6-35B-A3B-FP8"
LLMIS_NAME = os.environ.get("LLMIS_NAME", "qwen3-coder")
GATEWAY_NAME = "llm-d-gateway"
AI_GATEWAY_NAME = "maas-default-gateway"
AI_GATEWAY_NAMESPACE = "openshift-ingress"
AI_GATEWAY_HTTP_ROUTE = "pca-maas-front-door"
AI_GATEWAY_AUTH_POLICY = "pca-maas-apikey"
AI_GATEWAY_APIKEY_SECRET = "pca-maas-apikey"
AI_GATEWAY_APIKEY_KEY = "api_key"
GATEWAY_CLASS = "data-science-gateway-class"
WORKLOAD_SVC = os.environ.get(
    "WORKLOAD_SVC", f"{LLMIS_NAME}-kserve-workload-svc"
)
PVC_NAME = "model-cache"
GRAFANA_NAME = "pca-grafana"
LANGFUSE_ROUTE = "pca-langfuse"
LANGFUSE_SECRET = "pca-langfuse-credentials"
OTEL_NAME = "pca-otel-collector"
GUARDRAILS_PROXY = "guardrails-proxy"


def maas_gateway_class() -> str:
    """Gateway class for in-cluster MaaS DNS. Empty env keeps the Python default."""
    return os.environ.get("PCA_MAAS_GATEWAY_CLASS", "").strip() or GATEWAY_CLASS


def gateway_base(namespace: str) -> str:
    """llm-d Gateway ClusterIP (inference optimizer; escape-hatch / smoke harness)."""
    return (
        f"https://{GATEWAY_NAME}-{GATEWAY_CLASS}."
        f"{namespace}.svc.cluster.local"
    )


def gateway_v1(namespace: str) -> str:
    return f"{gateway_base(namespace)}/v1"


def ai_gateway_host() -> str:
    extra = os.environ.get("PCA_MAAS_HOSTNAME", "").strip()
    if extra:
        host = _http_hostname(extra)
        if host:
            return host
    return (
        f"{AI_GATEWAY_NAME}-{maas_gateway_class()}."
        f"{AI_GATEWAY_NAMESPACE}.svc.cluster.local"
    )


def ai_gateway_base(_namespace: str = "") -> str:
    """MaaS / RHCL Gateway (IDE front door with API key auth)."""
    return f"https://{ai_gateway_host()}"


def ai_gateway_v1(namespace: str = "") -> str:
    return f"{ai_gateway_base(namespace)}/v1"


def workload_base(namespace: str) -> str:
    # LLMIS workload Service is HTTPS when cluster enableLLMInferenceServiceTLS=true.
    return f"https://{WORKLOAD_SVC}.{namespace}.svc.cluster.local:8000"


def grafana_svc(namespace: str) -> str:
    return f"http://{GRAFANA_NAME}.{namespace}.svc.cluster.local:3000"


def langfuse_svc(namespace: str) -> str:
    return f"http://pca-langfuse-web.{namespace}.svc.cluster.local:3000"


def otel_health(namespace: str) -> str:
    return f"http://{OTEL_NAME}.{namespace}.svc.cluster.local:13133/"


def guardrails_proxy(namespace: str) -> str:
    return f"http://{GUARDRAILS_PROXY}.{namespace}.svc.cluster.local:8080"
