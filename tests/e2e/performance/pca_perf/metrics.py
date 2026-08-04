"""Generation-window metrics + report table."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WorkerResult:
    """One concurrent worker's generation window."""

    ok: bool
    tokens: int = 0
    generation_secs: float = 0.0
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
    gpu_util_pct: float | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def total_generation_s(self) -> float:
        """sum(tokens) / sum(generation_secs)."""
        if self.generation_secs <= 0:
            return 0.0
        return self.total_tokens / self.generation_secs


def stage_from_workers(
    name: str,
    n: int,
    workers: list[WorkerResult],
    *,
    gpu_util_pct: float | None = None,
) -> StageResult:
    ok = sum(1 for w in workers if w.ok)
    failed = sum(1 for w in workers if not w.ok)
    total_tokens = sum(w.tokens for w in workers if w.ok)
    generation_secs = sum(w.generation_secs for w in workers if w.ok)
    errors = [w.error for w in workers if w.error]
    return StageResult(
        name=name,
        n=n,
        ok=ok,
        failed=failed,
        total_tokens=total_tokens,
        generation_secs=generation_secs,
        gpu_util_pct=gpu_util_pct,
        errors=errors,
    )


def format_report(rows: list[StageResult]) -> str:
    headers = (
        "N",
        "stage",
        "ok/fail",
        "total_generation/s",
        "tokens",
        "gen secs",
        "GPU %",
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
                    f"{r.total_generation_s:.1f}",
                    str(r.total_tokens),
                    f"{r.generation_secs:.1f}",
                    gpu,
                ]
            )
        )
    err_lines: list[str] = []
    for r in rows:
        for err in r.errors[:3]:
            err_lines.append(f"  [{r.name} N={r.n}] {err}")
    if err_lines:
        lines.extend(["", "Sample errors:", *err_lines])
    return "\n".join(lines)


def usage_total_tokens(body: dict) -> int:
    """Extract total tokens from an OpenAI-style or OpenCode-ish response body."""
    for blob in (body.get("usage"), (body.get("info") or {}).get("usage")):
        if not isinstance(blob, dict):
            continue
        total = blob.get("total_tokens") or blob.get("total")
        if total is not None:
            try:
                return int(total)
            except (TypeError, ValueError):
                pass
        try:
            prompt = int(blob.get("prompt_tokens") or blob.get("input") or 0)
            completion = int(
                blob.get("completion_tokens") or blob.get("output") or 0
            )
            if prompt or completion:
                return prompt + completion
        except (TypeError, ValueError):
            continue
    info = body.get("info") or {}
    tokens = info.get("tokens")
    if isinstance(tokens, dict):
        try:
            return int(
                (tokens.get("total") or 0)
                or (
                    int(tokens.get("input") or 0) + int(tokens.get("output") or 0)
                )
            )
        except (TypeError, ValueError):
            pass
    return 0
