"""Cluster-internal and route URL builders."""

DEFAULT_MODEL_ID = "Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8"
LLMIS_NAME = "qwen3-coder"
GATEWAY_NAME = "llm-d-gateway"
AI_GATEWAY_NAME = "pca-ai-gateway"
AI_GATEWAY_HTTP_ROUTE = "pca-ai-gateway-local"
AI_GATEWAY_AUTH_POLICY = "pca-ai-gateway-apikey"
AI_GATEWAY_APIKEY_SECRET = "pca-ai-gw-apikey"
AI_GATEWAY_APIKEY_KEY = "api_key"
GATEWAY_CLASS = "data-science-gateway-class"
WORKLOAD_SVC = "qwen3-coder-kserve-workload-svc"
PVC_NAME = "model-cache"
GRAFANA_NAME = "pca-grafana"
LANGFUSE_ROUTE = "pca-langfuse"
LANGFUSE_SECRET = "pca-langfuse-credentials"
OTEL_NAME = "pca-otel-collector"
GUARDRAILS_PROXY = "guardrails-proxy"


def gateway_base(namespace: str) -> str:
    """llm-d Gateway ClusterIP (inference optimizer; escape-hatch / smoke harness)."""
    return (
        f"https://{GATEWAY_NAME}-{GATEWAY_CLASS}."
        f"{namespace}.svc.cluster.local"
    )


def gateway_v1(namespace: str) -> str:
    return f"{gateway_base(namespace)}/v1"


def ai_gateway_base(namespace: str) -> str:
    """RHCL AI Gateway ClusterIP (IDE front door with API key auth)."""
    return (
        f"https://{AI_GATEWAY_NAME}-{GATEWAY_CLASS}."
        f"{namespace}.svc.cluster.local"
    )


def ai_gateway_v1(namespace: str) -> str:
    return f"{ai_gateway_base(namespace)}/v1"


def workload_base(namespace: str) -> str:
    return f"https://{WORKLOAD_SVC}.{namespace}.svc.cluster.local:8000"


def grafana_svc(namespace: str) -> str:
    return f"http://{GRAFANA_NAME}.{namespace}.svc.cluster.local:3000"


def langfuse_svc(namespace: str) -> str:
    return f"http://pca-langfuse-web.{namespace}.svc.cluster.local:3000"


def otel_health(namespace: str) -> str:
    return f"http://{OTEL_NAME}.{namespace}.svc.cluster.local:13133/"


def guardrails_proxy(namespace: str) -> str:
    return f"http://{GUARDRAILS_PROXY}.{namespace}.svc.cluster.local:8080"
