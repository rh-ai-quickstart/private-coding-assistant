"""Generation-window metrics + report table."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WorkerResult:
    """One concurrent worker's generation window."""

    ok: bool
    tokens: int = 0
    generation_secs: float = 0.0
    gen_start: float | None = None
    gen_end: float | None = None
    ttft_secs: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    error: str | None = None

    @property
    def total_generation_s(self) -> float:
        if not self.ok or self.generation_secs <= 0:
            return 0.0
        return self.tokens / self.generation_secs


@dataclass
class StageResult:
    name: str
    n: int
    ok: int
    failed: int
    total_tokens: int
    generation_secs: float  # sum of per-worker generation windows
    wall_secs: float = 0.0  # max(gen_end) - min(gen_start) over ok workers
    prompt_tokens: int = 0
    completion_tokens: int = 0
    p50_gen_secs: float | None = None
    p95_gen_secs: float | None = None
    ttft_p50_secs: float | None = None
    ttft_p95_secs: float | None = None
    gpu_util_pct: float | None = None  # peak util sampled during the stage
    errors: list[str] = field(default_factory=list)

    @property
    def total_generation_s(self) -> float:
        """Busy-time average: sum(tokens) / sum(generation_secs)."""
        if self.generation_secs <= 0:
            return 0.0
        return self.total_tokens / self.generation_secs

    @property
    def vllm_tok_s(self) -> float:
        """System throughput under concurrency: sum(tokens) / wall_secs."""
        if self.wall_secs <= 0:
            return 0.0
        return self.total_tokens / self.wall_secs

    @property
    def parallel_efficiency(self) -> float | None:
        """sum(generation_secs) / (N * wall_secs). 1.0 = perfect overlap."""
        if self.ok <= 0 or self.wall_secs <= 0:
            return None
        return self.generation_secs / (self.ok * self.wall_secs)


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


def stage_from_workers(
    name: str,
    n: int,
    workers: list[WorkerResult],
    *,
    gpu_util_pct: float | None = None,
) -> StageResult:
    ok_workers = [w for w in workers if w.ok]
    ok = len(ok_workers)
    failed = sum(1 for w in workers if not w.ok)
    total_tokens = sum(w.tokens for w in ok_workers)
    generation_secs = sum(w.generation_secs for w in ok_workers)
    prompt_tokens = sum(w.prompt_tokens or 0 for w in ok_workers)
    completion_tokens = sum(w.completion_tokens or 0 for w in ok_workers)
    starts = [w.gen_start for w in ok_workers if w.gen_start is not None]
    ends = [w.gen_end for w in ok_workers if w.gen_end is not None]
    if starts and ends:
        wall_secs = max(max(ends) - min(starts), 1e-6)
    else:
        wall_secs = 0.0
    gen_vals = [w.generation_secs for w in ok_workers if w.generation_secs > 0]
    ttft_vals = [w.ttft_secs for w in ok_workers if w.ttft_secs is not None]
    errors = [w.error for w in workers if w.error]
    return StageResult(
        name=name,
        n=n,
        ok=ok,
        failed=failed,
        total_tokens=total_tokens,
        generation_secs=generation_secs,
        wall_secs=wall_secs,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        p50_gen_secs=_percentile(gen_vals, 50),
        p95_gen_secs=_percentile(gen_vals, 95),
        ttft_p50_secs=_percentile(ttft_vals, 50),
        ttft_p95_secs=_percentile(ttft_vals, 95),
        gpu_util_pct=gpu_util_pct,
        errors=errors,
    )


def _fmt(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}"


def format_report(rows: list[StageResult]) -> str:
    headers = (
        "N",
        "stage",
        "ok/fail",
        "vllm tok/s",
        "total_generation/s",
        "wall secs",
        "gen secs",
        "p50 gen",
        "p95 gen",
        "TTFT p50",
        "tokens",
        "prompt",
        "compl",
        "GPU peak %",
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
        lines.append(
            " | ".join(
                [
                    str(r.n),
                    r.name,
                    f"{r.ok}/{r.failed}",
                    f"{r.vllm_tok_s:.1f}",
                    f"{r.total_generation_s:.1f}",
                    f"{r.wall_secs:.1f}",
                    f"{r.generation_secs:.1f}",
                    _fmt(r.p50_gen_secs),
                    _fmt(r.p95_gen_secs),
                    _fmt(r.ttft_p50_secs),
                    str(r.total_tokens),
                    str(r.prompt_tokens),
                    str(r.completion_tokens),
                    gpu,
                ]
            )
        )
    footers: list[str] = []
    for r in rows:
        eff = r.parallel_efficiency
        if eff is None:
            continue
        ttft_p95 = _fmt(r.ttft_p95_secs)
        footers.append(
            f"  [{r.name} N={r.n}] parallel efficiency={eff:.2f}"
            f" (TTFT p95={ttft_p95})"
        )
    if footers:
        lines.extend(["", "Stage notes:", *footers])
    err_lines: list[str] = []
    for r in rows:
        for err in r.errors[:3]:
            err_lines.append(f"  [{r.name} N={r.n}] {err}")
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
