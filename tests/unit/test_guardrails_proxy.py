"""Unit tests for guardrails proxy outcome parsing, metrics, and Langfuse batch."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "charts"
    / "pca-ai-serving"
    / "charts"
    / "pca-guardrails"
    / "files"
    / "guardrails_proxy.py"
)

INPUT_SKIP = {
    "choices": [],
    "detections": {
        "input": [
            {
                "message_index": 0,
                "results": [
                    {
                        "detector_id": "prompt_injection",
                        "detection_type": "security",
                        "text": "ignore previous",
                        "score": 0.9,
                    }
                ],
            }
        ]
    },
    "warnings": [{"type": "UNSUITABLE_INPUT", "message": "Unsuitable input detected."}],
}

OUTPUT_FLAG = {
    "choices": [{"message": {"role": "assistant", "content": "print(1)"}}],
    "detections": {
        "output": [
            {
                "results": [
                    {
                        "detector_id": "regex",
                        "detection_type": "pii",
                        "detection": "email",
                        "text": "a@b.c",
                        "score": 1.0,
                    }
                ]
            }
        ]
    },
    "warnings": [{"type": "UNSUITABLE_OUTPUT"}],
}

ALLOWED = {
    "choices": [{"message": {"role": "assistant", "content": "hello"}}],
}


@pytest.fixture
def proxy():
    spec = importlib.util.spec_from_file_location("guardrails_proxy", _MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["guardrails_proxy"] = module
    spec.loader.exec_module(module)
    module._blocked_total = 0
    yield module
    module._blocked_total = 0


def test_parse_input_skip_is_block(proxy):
    outcome = proxy.parse_guardrails_outcome(INPUT_SKIP)
    assert outcome.action == "block"
    assert len(outcome.hits) == 1
    assert outcome.hits[0].detector_id == "prompt_injection"
    assert outcome.hits[0].direction == "input"


def test_parse_output_flag_is_warn(proxy):
    outcome = proxy.parse_guardrails_outcome(OUTPUT_FLAG)
    assert outcome.action == "warn"
    assert outcome.hits[0].detection_type == "pii"
    assert outcome.hits[0].direction == "output"


def test_parse_allowed_is_empty_action(proxy):
    outcome = proxy.parse_guardrails_outcome(ALLOWED)
    assert outcome.action == ""
    assert outcome.hits == ()


def test_parse_non_dict_is_allowed(proxy):
    assert proxy.parse_guardrails_outcome(None).action == ""
    assert proxy.parse_guardrails_outcome([]).action == ""


def test_record_outcome_counts_only_blocks(proxy):
    proxy.record_outcome(proxy.parse_guardrails_outcome(ALLOWED))
    proxy.record_outcome(proxy.parse_guardrails_outcome(OUTPUT_FLAG))
    assert proxy._blocked_total == 0
    proxy.record_outcome(proxy.parse_guardrails_outcome(INPUT_SKIP))
    proxy.record_outcome(proxy.parse_guardrails_outcome(INPUT_SKIP))
    assert proxy._blocked_total == 2
    text = proxy.metrics_text()
    assert "pca_guardrails_blocked_total 2" in text
    assert "# TYPE pca_guardrails_blocked_total counter" in text


def test_sse_block_uses_outcome_hits(proxy):
    sse = proxy.completion_to_sse_chunks(INPUT_SKIP)
    assert "Guardrails blocked your message" in sse
    assert "Prompt injection detected" in sse
    assert "data: [DONE]" in sse


def test_sse_output_flag_keeps_model_text(proxy):
    sse = proxy.completion_to_sse_chunks(OUTPUT_FLAG)
    assert "print(1)" in sse
    assert "Guardrails blocked your message" not in sse


def test_langfuse_batch_tags_blocked(proxy):
    outcome = proxy.parse_guardrails_outcome(INPUT_SKIP)
    payload = proxy.langfuse_flagged_batch(
        {"model": "m", "messages": [{"role": "user", "content": "jailbreak"}]},
        INPUT_SKIP,
        outcome,
        {"X-PCA-User": "dev-user1", "X-PCA-DevSpace": "dev-user1-devspaces"},
    )
    traces = [e for e in payload["batch"] if e["type"] == "trace-create"]
    assert len(traces) == 1
    body = traces[0]["body"]
    assert body["name"] == "guardrails-flagged"
    assert body["userId"] == "dev-user1"
    assert "guardrails:flagged" in body["tags"]
    assert "guardrails:blocked" in body["tags"]
    assert "devspace:dev-user1-devspaces" in body["tags"]
    assert "jailbreak" in json.dumps(body["input"])
    assert "Guardrails blocked" in body["output"]
    assert body["metadata"]["action"] == "block"
    assert body["metadata"]["hits"][0]["detector_id"] == "prompt_injection"


def test_langfuse_batch_tags_warned(proxy):
    outcome = proxy.parse_guardrails_outcome(OUTPUT_FLAG)
    payload = proxy.langfuse_flagged_batch(
        {"messages": [{"role": "user", "content": "write code"}]},
        OUTPUT_FLAG,
        outcome,
        {},
    )
    body = payload["batch"][0]["body"]
    assert "guardrails:warned" in body["tags"]
    assert "guardrails:blocked" not in body["tags"]


def test_schedule_langfuse_skips_without_keys(proxy):
    outcome = proxy.parse_guardrails_outcome(INPUT_SKIP)
    with patch.dict("os.environ", {"LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": ""}, clear=False):
        with patch.object(proxy, "_EMIT_POOL") as pool:
            proxy.schedule_flagged_langfuse({}, INPUT_SKIP, outcome, {})
            pool.submit.assert_not_called()


def test_schedule_langfuse_skips_allowed(proxy, monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    outcome = proxy.parse_guardrails_outcome(ALLOWED)
    with patch.object(proxy, "_EMIT_POOL") as pool:
        proxy.schedule_flagged_langfuse({}, ALLOWED, outcome, {})
        pool.submit.assert_not_called()
