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
