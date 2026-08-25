"""Route-class table for MaaS front-door e2e cases."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, assert_never

from pca_e2e import oc

RouteClass = Literal["chat-guarded", "tab-local", "passthrough"]
PayloadKind = Literal["none", "pong", "count", "secret"]

DEFAULT_MODEL_ID = "Qwen/Qwen3.6-35B-A3B-FP8"


@dataclass(frozen=True)
class RouteCase:
    id: str
    route_class: RouteClass
    path: str
    method: str
    stream: bool
    payload: PayloadKind
    expect_status: int
    expect_blocked: bool | None
    max_ttfb_secs: float | None = None
    skip_if: Callable[[str], str | None] | None = None


def origin_from_base_url(base: str) -> str:
    value = base or ""
    while value.endswith("/"):
        value = value[:-1]
    if value.endswith("/v1"):
        return value[: -len("/v1")]
    return value


def skip_unless_guardrails(ai_namespace: str) -> str | None:
    if not oc.resource_exists("svc", "guardrails-proxy", namespace=ai_namespace):
        return f"guardrails-proxy Service missing in {ai_namespace}"
    return None


def skip_if_semantic_router_present(ai_namespace: str) -> str | None:
    if oc.resource_exists(
        "svc", "pca-semantic-router", namespace=ai_namespace
    ) or oc.resource_exists("svc", "semantic-router", namespace=ai_namespace):
        return f"semantic router Service present in {ai_namespace}"
    return None


def model_id_from_pod(namespace: str, pod: str) -> str:
    result = oc.exec_in_pod(
        namespace,
        pod,
        "bash",
        "-lc",
        "python3 -c \"import os; print(os.environ.get('VLLM_MODEL_ID') "
        "or os.environ.get('OPENAI_MODEL') or '')\"",
        timeout=30,
    )
    return (result.stdout or "").strip() or DEFAULT_MODEL_ID


def json_body_for(case: RouteCase, model_id: str) -> dict[str, Any] | None:
    if case.payload == "none":
        return None
    if case.payload == "pong":
        content = "Reply with the single word pong."
        max_tokens = 16
    elif case.payload == "count":
        content = "Count from 1 to 40, one number per line, digits only."
        max_tokens = 128
    elif case.payload == "secret":
        content = (
            "key = AKIAIOSFODNN7EXAMPLE. Reply with the single word pong."
        )
        max_tokens = 16
    else:
        assert_never(case.payload)
    return {
        "model": model_id,
        "messages": [{"role": "user", "content": content}],
        "stream": case.stream,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
    }


ROUTE_CASES: tuple[RouteCase, ...] = (
    RouteCase(
        id="chat-guarded-pong",
        route_class="chat-guarded",
        path="/v1/chat/completions",
        method="POST",
        stream=False,
        payload="pong",
        expect_status=200,
        expect_blocked=False,
    ),
    RouteCase(
        id="chat-guarded-stream-ttfb",
        route_class="chat-guarded",
        path="/v1/chat/completions",
        method="POST",
        stream=True,
        payload="count",
        expect_status=200,
        expect_blocked=False,
        max_ttfb_secs=0.75,
    ),
    RouteCase(
        id="chat-guarded-secret-stream",
        route_class="chat-guarded",
        path="/v1/chat/completions",
        method="POST",
        stream=True,
        payload="secret",
        expect_status=200,
        expect_blocked=True,
        skip_if=skip_unless_guardrails,
    ),
    RouteCase(
        id="tab-local-secret",
        route_class="tab-local",
        path="/local/v1/chat/completions",
        method="POST",
        stream=False,
        payload="secret",
        expect_status=200,
        expect_blocked=False,
        skip_if=skip_unless_guardrails,
    ),
    RouteCase(
        id="passthrough-models",
        route_class="passthrough",
        path="/v1/models",
        method="GET",
        stream=False,
        payload="none",
        expect_status=200,
        expect_blocked=None,
    ),
    RouteCase(
        id="sr-off-chat-still-local",
        route_class="chat-guarded",
        path="/v1/chat/completions",
        method="POST",
        stream=False,
        payload="pong",
        expect_status=200,
        expect_blocked=False,
        skip_if=skip_if_semantic_router_present,
    ),
)
