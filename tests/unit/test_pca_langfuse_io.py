"""Unit tests for Langfuse I/O middleware usage parsing."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "PCA_Deployment_ROSA"
    / "charts"
    / "pca-ai-serving"
    / "files"
    / "pca_langfuse_io.py"
)


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("pca_langfuse_io", _MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["pca_langfuse_io"] = module
    spec.loader.exec_module(module)
    return module


def test_usage_from_non_stream_json(mod):
    body = json.dumps(
        {
            "choices": [{"message": {"content": "hi"}}],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }
    ).encode()
    assert mod._usage_from_response(body) == {
        "input": 10,
        "output": 5,
        "total": 15,
    }


def test_usage_from_sse_with_final_usage_chunk(mod):
    body = (
        'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"lo"},"finish_reason":"stop"}]}\n\n'
        'data: {"choices":[],"usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15}}\n\n'
        "data: [DONE]\n\n"
    ).encode()
    assert mod._usage_from_response(body) == {
        "input": 10,
        "output": 5,
        "total": 15,
    }


def test_usage_from_sse_without_usage(mod):
    body = (
        'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
        "data: [DONE]\n\n"
    ).encode()
    assert mod._usage_from_response(body) is None


def test_usage_from_empty_and_malformed(mod):
    assert mod._usage_from_response(b"") is None
    assert mod._usage_from_response(b"   ") is None
    assert mod._usage_from_response(b"not-json") is None
