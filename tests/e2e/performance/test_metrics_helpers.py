"""Pure-python checks for ladder prefill/decode aggregation (no cluster)."""

from __future__ import annotations

from pca_e2e.opencode import _event_is_assistant_text
from pca_perf.metrics import WorkerResult, format_report, stage_from_workers


def test_event_is_assistant_text_accepts_text_delta() -> None:
    assert _event_is_assistant_text({"type": "text-delta", "sessionID": "s1"})
    assert _event_is_assistant_text(
        {
            "type": "message.part.updated",
            "properties": {"part": {"type": "text", "text": "hello"}},
        }
    )


def test_event_is_assistant_text_rejects_tool_and_reasoning() -> None:
    assert not _event_is_assistant_text(
        {
            "type": "message.part.updated",
            "properties": {"part": {"type": "tool", "tool": "bash"}},
        }
    )
    assert not _event_is_assistant_text(
        {
            "type": "message.part.updated",
            "properties": {"part": {"type": "reasoning", "text": "thinking"}},
        }
    )
    assert not _event_is_assistant_text(
        {
            "type": "message.part.updated",
            "properties": {"part": {"type": "text", "text": "   "}},
        }
    )


def test_model_ids_from_devworkspace_reads_vllm_env() -> None:
    from pca_perf.opencode_run import _model_ids_from_devworkspace

    dw = {
        "spec": {
            "template": {
                "components": [
                    {
                        "container": {
                            "env": [
                                {"name": "VLLM_MODEL_ID", "value": "Qwen/Test"},
                            ]
                        }
                    }
                ]
            }
        }
    }
    assert _model_ids_from_devworkspace(dw) == ("vllm", "Qwen/Test")
    assert _model_ids_from_devworkspace({"spec": {}}) is None


def test_stage_averages_prefill_decode_ok_workers_only() -> None:
    workers = [
        WorkerResult(
            ok=True,
            generation_secs=10.0,
            gen_start=1.0,
            gen_end=11.0,
            worker_start=0.0,
            worker_end=12.0,
            prefill_secs=2.0,
            decode_secs=8.0,
            completion_tokens=100,
            llm_calls=2,
        ),
        WorkerResult(
            ok=True,
            generation_secs=12.0,
            gen_start=1.5,
            gen_end=13.5,
            worker_start=0.1,
            worker_end=14.0,
            prefill_secs=4.0,
            decode_secs=6.0,
            completion_tokens=80,
            llm_calls=1,
        ),
        WorkerResult(ok=False, error="boom"),
    ]
    stage = stage_from_workers(
        3, workers, gpu_util_pct=40.0, gpu_mean_util_pct=22.0
    )
    assert stage.ok == 2
    assert stage.failed == 1
    assert stage.avg_prefill_secs == 3.0
    assert stage.avg_decode_secs == 7.0
    assert stage.gpu_util_pct == 40.0
    assert stage.gpu_mean_util_pct == 22.0
    report = format_report([stage])
    assert "avg prefill time per user (sec)" in report
    assert "avg decode time per user (sec)" in report
    assert "mean GPU utilization (%)" in report
    assert "3.0" in report
    assert "7.0" in report
    assert "22" in report
    assert "avg first LLM call per user (sec)" in report
    assert "avg last LLM call per user (sec)" in report
    assert "avg guardrails overhead per conversation (sec)" in report
    assert "avg semantic-router hop per conversation (sec)" in report
    assert report.count(" | - |") >= 1 or " - " in report


def test_stage_averages_first_last_llm_calls_and_skips_missing() -> None:
    workers = [
        WorkerResult(
            ok=True,
            generation_secs=10.0,
            gen_start=1.0,
            gen_end=11.0,
            worker_start=0.0,
            worker_end=12.0,
            prefill_secs=1.0,
            decode_secs=9.0,
            completion_tokens=50,
            llm_calls=2,
            first_llm_call_secs=2.0,
            last_llm_call_secs=4.0,
        ),
        WorkerResult(
            ok=True,
            generation_secs=8.0,
            gen_start=1.0,
            gen_end=9.0,
            worker_start=0.0,
            worker_end=10.0,
            prefill_secs=1.0,
            decode_secs=7.0,
            completion_tokens=40,
            llm_calls=1,
            first_llm_call_secs=3.0,
            last_llm_call_secs=None,
        ),
        WorkerResult(ok=False, error="nope"),
    ]
    stage = stage_from_workers(
        3, workers, guardrails_overhead_secs=0.4, semantic_router_hop_secs=0.2
    )
    assert stage.avg_first_llm_call_secs == 2.5
    assert stage.avg_last_llm_call_secs == 4.0
    assert stage.avg_guardrails_overhead_secs == 0.4
    assert stage.avg_semantic_router_hop_secs == 0.2
    report = format_report([stage])
    assert "2.5" in report
    assert "4.0" in report
    assert "0.4" in report
    assert "0.2" in report


def test_stage_guardrails_absent_prints_dash() -> None:
    workers = [
        WorkerResult(
            ok=True,
            generation_secs=5.0,
            gen_start=1.0,
            gen_end=6.0,
            worker_start=0.0,
            worker_end=7.0,
            prefill_secs=1.0,
            decode_secs=4.0,
            completion_tokens=10,
            llm_calls=1,
        )
    ]
    stage = stage_from_workers(1, workers)
    assert stage.avg_first_llm_call_secs is None
    assert stage.avg_last_llm_call_secs is None
    assert stage.avg_guardrails_overhead_secs is None
    assert stage.avg_semantic_router_hop_secs is None
    report = format_report([stage])
    assert "avg first LLM call per user (sec)" in report
    assert "avg guardrails overhead per conversation (sec)" in report
    assert "avg semantic-router hop per conversation (sec)" in report


def test_durations_from_messages_uses_completed_minus_created() -> None:
    from pca_e2e.opencode import durations_from_messages

    messages = [
        {
            "info": {
                "role": "user",
                "time": {"created": 1000, "completed": 1100},
                "tokens": {"output": 0},
            }
        },
        {
            "info": {
                "role": "assistant",
                "time": {"created": 2000, "completed": 4900},
                "tokens": {"output": 80},
            }
        },
        {
            "info": {
                "role": "assistant",
                "time": {"created": 5000, "completed": 8400},
                "tokens": {"output": 20},
            }
        },
        {
            "info": {
                "role": "assistant",
                "time": {"created": 9000},
                "tokens": {"output": 5},
            }
        },
    ]
    assert durations_from_messages(messages) == [2.9, 3.4]


def test_parse_overhead_seconds_reads_prometheus_counter() -> None:
    from pca_perf.guardrails import parse_overhead_seconds

    text = (
        "# HELP pca_guardrails_overhead_seconds_total x\n"
        "# TYPE pca_guardrails_overhead_seconds_total counter\n"
        "pca_guardrails_overhead_seconds_total 1.25\n"
        "pca_guardrails_blocked_total 2\n"
    )
    assert parse_overhead_seconds(text) == 1.25
    assert parse_overhead_seconds("# TYPE pca_guardrails_blocked_total counter\n") is None


def test_parse_hop_seconds_reads_prometheus_counter() -> None:
    from pca_perf.semantic_router import parse_hop_seconds

    text = (
        "# HELP pca_semantic_router_hop_seconds_total x\n"
        "# TYPE pca_semantic_router_hop_seconds_total counter\n"
        "pca_semantic_router_hop_seconds_total 0.08\n"
        'pca_semantic_router_decisions_total{backend="local"} 3\n'
    )
    assert parse_hop_seconds(text) == 0.08
    assert parse_hop_seconds("# TYPE pca_semantic_router_decisions_total counter\n") is None
