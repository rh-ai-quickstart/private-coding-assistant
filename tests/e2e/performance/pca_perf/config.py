"""Env / constants for performance ladder runs."""

from __future__ import annotations

import os

AI_GATEWAY_NAME = "pca-ai-gateway"
AI_GATEWAY_APIKEY_SECRET = "pca-ai-gw-apikey"
AI_GATEWAY_APIKEY_KEY = "api_key"
REPO_URL = "https://github.com/rh-ai-quickstart/multimodal-compliance-monitor"
REPO_DIR = "/projects/multimodal-compliance-monitor"


def ai_namespace() -> str:
    return os.environ.get("AI_NAMESPACE", "private-assistant-ai-serving").strip()


def model_name() -> str:
    """InferenceService / LLMInferenceService name (chart model.name)."""
    return os.environ.get("MODEL_NAME", "qwen3-coder").strip()


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


def opencode_timeout_secs() -> float:
    # Default fits the short TODO-file probe (not a full feature build).
    return float(os.environ.get("PERF_OPENCODE_TIMEOUT", "300"))
