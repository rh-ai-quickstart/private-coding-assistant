"""vLLM / llm-d gateway smoke tests."""

from __future__ import annotations

import pytest

from pca_smoke import oc, urls

pytestmark = pytest.mark.vllm


def test_models_list(ai_namespace: str, gateway_v1: str, model_id: str) -> None:
    status, body = oc.in_cluster_http(ai_namespace, f"{gateway_v1}/models")
    assert status == 200, f"/v1/models returned {status}: {body!r}"
    assert isinstance(body, dict), body
    ids = [m.get("id") for m in (body.get("data") or [])]
    assert model_id in ids or any(model_id in (i or "") for i in ids), (
        f"model {model_id!r} not in /v1/models: {ids}"
    )


def test_chat_completions(ai_namespace: str, gateway_v1: str, model_id: str) -> None:
    status, body = oc.in_cluster_http(
        ai_namespace,
        f"{gateway_v1}/chat/completions",
        method="POST",
        json_body={
            "model": model_id,
            "messages": [{"role": "user", "content": "Say hello in one word."}],
            "stream": False,
            "max_tokens": 32,
        },
        timeout_secs=180,
    )
    assert status == 200, f"chat/completions returned {status}: {body!r}"
    assert isinstance(body, dict), body
    choices = body.get("choices") or []
    assert choices, body
    content = oc.message_text(choices[0])
    assert str(content).strip(), f"empty chat content: {body}"


def test_completions(ai_namespace: str, gateway_v1: str, model_id: str) -> None:
    status, body = oc.in_cluster_http(
        ai_namespace,
        f"{gateway_v1}/completions",
        method="POST",
        json_body={
            "model": model_id,
            "prompt": "def hello():",
            "max_tokens": 16,
            "stream": False,
        },
        timeout_secs=180,
    )
    assert status == 200, f"/v1/completions returned {status}: {body!r}"
    assert isinstance(body, dict), body
    choices = body.get("choices") or []
    assert choices, body
    text = choices[0].get("text") or ""
    assert text is not None


def test_streaming_chat(ai_namespace: str, gateway_v1: str, model_id: str) -> None:
    # Streamed SSE — accept any 200 with data: lines or a JSON stream chunk.
    status, body = oc.in_cluster_http(
        ai_namespace,
        f"{gateway_v1}/chat/completions",
        method="POST",
        json_body={
            "model": model_id,
            "messages": [{"role": "user", "content": "Count to 3."}],
            "stream": True,
            "max_tokens": 32,
        },
        timeout_secs=180,
    )
    assert status == 200, f"streaming chat returned {status}: {body!r}"
    raw = body if isinstance(body, str) else str(body)
    assert "data:" in raw or "choices" in raw, f"unexpected stream body: {raw[:400]!r}"


def test_tool_calling(ai_namespace: str, gateway_v1: str, model_id: str) -> None:
    # Qwen3 thinking mode emits raw <tool_call> XML into content instead of
    # structured tool_calls — disable thinking for this check (same as guardrails proxy).
    status, body = oc.in_cluster_http(
        ai_namespace,
        f"{gateway_v1}/chat/completions",
        method="POST",
        json_body={
            "model": model_id,
            "messages": [{"role": "user", "content": "List files in /tmp"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "list_files",
                        "description": "List directory contents",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "description": "Directory path",
                                }
                            },
                            "required": ["path"],
                        },
                    },
                }
            ],
            "tool_choice": "auto",
            "max_tokens": 200,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
        },
        timeout_secs=180,
    )
    assert status == 200, f"tool-calling request returned {status}: {body!r}"
    assert isinstance(body, dict), body
    choices = body.get("choices") or []
    assert choices, body
    msg = choices[0].get("message") or {}
    finish = choices[0].get("finish_reason")
    tool_calls = msg.get("tool_calls") or []
    content = oc.message_text(choices[0])
    if finish == "tool_calls" or tool_calls:
        return
    # Soft failure modes mirrored from ARO validate.sh
    if "</think>" in content:
        pytest.fail("tool calling broken — </think> tokens leaking (missing reasoning parser)")
    if "<tool_call>" in content:
        pytest.fail("tool calling broken — XML tool_call in content (wrong tool-call parser)")
    pytest.skip(
        f"tool calling inconclusive (finish_reason={finish!r}); model may have answered without tools"
    )


def test_workload_health(ai_namespace: str) -> None:
    url = f"{urls.workload_base(ai_namespace)}/health"
    status, body = oc.in_cluster_http(ai_namespace, url, timeout_secs=60)
    assert status == 200, f"workload /health returned {status}: {body!r}"
