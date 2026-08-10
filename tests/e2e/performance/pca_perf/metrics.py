"""OpenCode ladder metrics + report table."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WorkerResult:
    """One concurrent OpenCode worker."""

    ok: bool
    generation_secs: float = 0.0
    gen_start: float | None = None
    gen_end: float | None = None
    worker_start: float | None = None  # includes setup (clone, DW, session)
    worker_end: float | None = None
    prefill_secs: float = 0.0  # prompt send → first assistant text (TTFT)
    decode_secs: float = 0.0  # first text → turn end (may include tools)
    completion_tokens: int = 0
    llm_calls: int = 0
    error: str | None = None

    @property
    def req_output_tok_s(self) -> float | None:
        if not self.ok or self.generation_secs <= 0 or self.completion_tokens <= 0:
            return None
        return self.completion_tokens / self.generation_secs


@dataclass
class StageResult:
    n: int
    ok: int
    failed: int
    makespan_secs: float = 0.0
    gen_span_secs: float = 0.0
    overhead_secs: float = 0.0
    avg_prefill_secs: float | None = None
    avg_decode_secs: float | None = None
    output_tokens: int = 0
    avg_output_tokens: float = 0.0
    e2e_output_tok_s: float = 0.0
    avg_req_output_tok_s: float | None = None
    p50_req_output_tok_s: float | None = None
    p95_req_output_tok_s: float | None = None
    llm_calls: int = 0
    avg_llm_calls: float = 0.0
    gpu_util_pct: float | None = None
    gpu_mean_util_pct: float | None = None
    errors: list[str] = field(default_factory=list)


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    rank = (len(xs) - 1) * (pct / 100.0)
    lo = int(rank)
    hi = min(lo + 1, len(xs) - 1)
    frac = rank - lo
    return xs[lo] + (xs[hi] - xs[lo]) * frac


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def stage_from_workers(
    n: int,
    workers: list[WorkerResult],
    *,
    gpu_util_pct: float | None = None,
    gpu_mean_util_pct: float | None = None,
) -> StageResult:
    ok_workers = [w for w in workers if w.ok]
    ok = len(ok_workers)
    failed = sum(1 for w in workers if not w.ok)
    output_tokens = sum(w.completion_tokens for w in ok_workers)
    llm_calls = sum(w.llm_calls for w in ok_workers)

    gen_starts = [w.gen_start for w in ok_workers if w.gen_start is not None]
    gen_ends = [w.gen_end for w in ok_workers if w.gen_end is not None]
    if gen_starts and gen_ends:
        gen_span_secs = max(max(gen_ends) - min(gen_starts), 1e-6)
    else:
        gen_span_secs = 0.0

    worker_starts = [
        w.worker_start for w in ok_workers if w.worker_start is not None
    ]
    worker_ends = [w.worker_end for w in ok_workers if w.worker_end is not None]
    if worker_starts and worker_ends:
        makespan_secs = max(max(worker_ends) - min(worker_starts), 1e-6)
    else:
        makespan_secs = 0.0
    overhead_secs = max(makespan_secs - gen_span_secs, 0.0)

    rates = [
        r
        for w in ok_workers
        if (r := w.req_output_tok_s) is not None
    ]
    prefills = [w.prefill_secs for w in ok_workers if w.prefill_secs > 0]
    decodes = [w.decode_secs for w in ok_workers if w.decode_secs > 0]
    e2e = (output_tokens / makespan_secs) if makespan_secs > 0 else 0.0
    errors = [w.error for w in workers if w.error]
    return StageResult(
        n=n,
        ok=ok,
        failed=failed,
        makespan_secs=makespan_secs,
        gen_span_secs=gen_span_secs,
        overhead_secs=overhead_secs,
        avg_prefill_secs=_mean(prefills),
        avg_decode_secs=_mean(decodes),
        output_tokens=output_tokens,
        avg_output_tokens=(output_tokens / ok) if ok else 0.0,
        e2e_output_tok_s=e2e,
        avg_req_output_tok_s=_mean(rates),
        p50_req_output_tok_s=_percentile(rates, 50),
        p95_req_output_tok_s=_percentile(rates, 95),
        llm_calls=llm_calls,
        avg_llm_calls=(llm_calls / ok) if ok else 0.0,
        gpu_util_pct=gpu_util_pct,
        gpu_mean_util_pct=gpu_mean_util_pct,
        errors=errors,
    )


def _fmt(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}"


def format_report(rows: list[StageResult]) -> str:
    headers = (
        "concurrent users (N)",
        "succeeded / failed",
        "end-to-end output tokens/sec (incl. setup)",
        "avg per-user output tokens/sec (generation only)",
        "p50 per-user output tokens/sec (generation only)",
        "p95 per-user output tokens/sec (generation only)",
        "total stage time (sec)",
        "active generation window (sec)",
        "non-generation overhead (sec)",
        "avg prefill time per user (sec)",
        "avg decode time per user (sec)",
        "total output tokens",
        "avg output tokens per user",
        "total LLM model calls",
        "avg LLM model calls per user",
        "peak GPU utilization (%)",
        "mean GPU utilization (%)",
    )
    lines = [
        "Performance ladder results",
        "==========================",
        "",
        " | ".join(headers),
        " | ".join("---" for _ in headers),
    ]
    for r in rows:
        gpu = f"{r.gpu_util_pct:.0f}" if r.gpu_util_pct is not None else "n/a"
        gpu_mean = (
            f"{r.gpu_mean_util_pct:.0f}"
            if r.gpu_mean_util_pct is not None
            else "n/a"
        )
        lines.append(
            " | ".join(
                [
                    str(r.n),
                    f"{r.ok}/{r.failed}",
                    f"{r.e2e_output_tok_s:.1f}",
                    _fmt(r.avg_req_output_tok_s),
                    _fmt(r.p50_req_output_tok_s),
                    _fmt(r.p95_req_output_tok_s),
                    f"{r.makespan_secs:.1f}",
                    f"{r.gen_span_secs:.1f}",
                    f"{r.overhead_secs:.1f}",
                    _fmt(r.avg_prefill_secs),
                    _fmt(r.avg_decode_secs),
                    str(r.output_tokens),
                    f"{r.avg_output_tokens:.1f}",
                    str(r.llm_calls),
                    f"{r.avg_llm_calls:.1f}",
                    gpu,
                    gpu_mean,
                ]
            )
        )
    err_lines: list[str] = []
    for r in rows:
        for err in r.errors[:3]:
            err_lines.append(f"  [N={r.n}] {err}")
    if err_lines:
        lines.extend(["", "Sample errors:", *err_lines])
    return "\n".join(lines)


def usage_token_parts(body: dict) -> tuple[int, int, int]:
    """Return (prompt_tokens, completion_tokens, total_tokens) from a response body.

    Missing parts are 0. total falls back to prompt+completion when needed.
    """
    for blob in (body.get("usage"), (body.get("info") or {}).get("usage")):
        if not isinstance(blob, dict):
            continue
        prompt = 0
        completion = 0
        try:
            prompt = int(blob.get("prompt_tokens") or blob.get("input") or 0)
            completion = int(
                blob.get("completion_tokens") or blob.get("output") or 0
            )
        except (TypeError, ValueError):
            prompt = 0
            completion = 0
        total: int | None = None
        raw_total = blob.get("total_tokens") or blob.get("total")
        if raw_total is not None:
            try:
                total = int(raw_total)
            except (TypeError, ValueError):
                total = None
        if total is None:
            total = prompt + completion
        if prompt or completion or total:
            return prompt, completion, total
    info = body.get("info") or {}
    tokens = info.get("tokens")
    if isinstance(tokens, dict):
        try:
            prompt = int(tokens.get("input") or 0)
            completion = int(tokens.get("output") or 0)
            total = int(tokens.get("total") or 0) or (prompt + completion)
            if prompt or completion or total:
                return prompt, completion, total
        except (TypeError, ValueError):
            pass
    return 0, 0, 0


def usage_total_tokens(body: dict) -> int:
    """Extract total tokens from an OpenAI-style or OpenCode-ish response body."""
    _, _, total = usage_token_parts(body)
    return total
