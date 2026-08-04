"""Env / constants for performance ladder runs."""

from __future__ import annotations

import os

DEFAULT_MODEL_ID = "Qwen/Qwen3.6-35B-A3B-FP8"
LLMIS_NAME = "qwen3-coder"
AI_GATEWAY_NAME = "pca-ai-gateway"
GATEWAY_CLASS = "data-science-gateway-class"
AI_GATEWAY_APIKEY_SECRET = "pca-ai-gw-apikey"
AI_GATEWAY_APIKEY_KEY = "api_key"
REPO_URL = "https://github.com/rh-ai-quickstart/multimodal-compliance-monitor"
REPO_DIR = "/projects/multimodal-compliance-monitor"

# Coding-like medium prompt for gateway concurrency probe.
GATEWAY_PROMPT = (
    "You are a coding assistant. Write a Python function "
    "def fibonacci(n: int) -> int that returns the nth Fibonacci number "
    "using iteration. Include a one-line docstring. Reply with code only."
)


def ai_namespace() -> str:
    return os.environ.get("AI_NAMESPACE", "private-assistant-ai-serving").strip()


def parse_n_list(raw: str | None = None) -> list[int]:
    text = (raw if raw is not None else os.environ.get("N_LIST", "1")).strip()
    if not text:
        raise ValueError("N_LIST is empty — pass e.g. N_LIST=1,2,4")
    values: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        n = int(part)
        if n < 1:
            raise ValueError(f"N_LIST entries must be >= 1, got {n}")
        values.append(n)
    if not values:
        raise ValueError("N_LIST has no valid integers")
    # Preserve order, drop duplicates
    seen: set[int] = set()
    out: list[int] = []
    for n in values:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def user_namespace(index: int) -> str:
    """1-based index → dev-user{i}-devspaces."""
    return f"dev-user{index}-devspaces"


def ai_gateway_service_name() -> str:
    return f"{AI_GATEWAY_NAME}-{GATEWAY_CLASS}"


def gateway_chat_timeout_secs() -> float:
    return float(os.environ.get("PERF_GATEWAY_TIMEOUT", "180"))


def opencode_timeout_secs() -> float:
    # Default fits the short TODO-file probe (not a full feature build).
    return float(os.environ.get("PERF_OPENCODE_TIMEOUT", "180"))


def gateway_max_tokens() -> int:
    return int(os.environ.get("PERF_GATEWAY_MAX_TOKENS", "128"))
