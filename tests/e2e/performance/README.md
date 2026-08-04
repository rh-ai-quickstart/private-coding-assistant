# Performance / scalability ladder

Measures how many developers the stack can serve at once.

## Important limitation

The OpenCode stage is a **load probe**, not a real feature test.

Each agent only creates `MODEL_REGISTRY_TODO.md` (a short TODO about Model Registry).
It does **not** integrate OpenShift AI Model Registry into the app.
Use this suite for throughput / concurrency metrics only.

## Metrics

### Generation window (per worker)

```text
generation_secs = first output frame → generation finished
```

**Included:** model decode, tool calls/results, further agent turns until the chat/agent turn completes.

**Excluded:** DevWorkspace start, `git clone`, port-forward setup, `/v1/models` probe, session create, health checks.

- **Gateway:** clock starts at the first SSE content chunk; ends when the stream closes.
- **OpenCode:** clock starts at the first `/event` SSE activity frame for the session; ends when the agent turn returns (tools included).

### Stage columns

| Column | Definition |
|--------|------------|
| `wall secs` | `max(gen_end) - min(gen_start)` over successful workers — parallel stage duration |
| `gen secs` | **sum** of per-worker `generation_secs` (busy time, not wall) |
| `vllm tok/s` | `sum(tokens) / wall_secs` — system throughput under concurrency (path is still gateway/OpenCode → vLLM) |
| `total_generation/s` | `sum(tokens) / sum(generation_secs)` — busy-time average (not parallel throughput) |
| `p50 gen` / `p95 gen` | percentiles of per-worker `generation_secs` |
| `TTFT p50` | gateway only: request-send → first content chunk (`-` for OpenCode) |
| `tokens` / `prompt` / `compl` | totals; prompt/completion when usage splits are available |
| `GPU peak %` | peak `nvidia-smi` util sampled every ~2s **during** the stage |

Footer per stage:

```text
parallel efficiency = sum(generation_secs) / (ok_workers * wall_secs)
```

`1.0` = perfect overlap; dropping values mean stragglers or serialization.
TTFT p95 is also printed in the footer when available.

### How to read the ladder

As `N` grows:

1. Watch **`vllm tok/s` rise then flatten** — that plateau is serving capacity under concurrency.
2. Watch **`p95 gen` / TTFT p95 grow** — latency stretch / queueing under load.
3. Keep **`total_generation/s`** for per-worker busy-time rate; do not treat it as parallel system throughput.

Gateway vs OpenCode workloads still differ in size — compare each stage across N, not gateway tok rate vs OpenCode tok rate as equals.

## What it does

For each `N` in `N_LIST`:

1. **Gateway** — `N` parallel streaming `/v1/chat/completions` through `pca-ai-gateway`
2. **OpenCode** — `N` pre-deployed users (`dev-user1` … `dev-userN`) each clone
   [multimodal-compliance-monitor](https://github.com/rh-ai-quickstart/multimodal-compliance-monitor)
   and run one short agent turn (create `MODEL_REGISTRY_TODO.md`) for load

## Prerequisites

- `oc` logged in, `uv` available
- AI serving with `pca-ai-gateway` in `AI_NAMESPACE`
- OpenCode DevSpaces already deployed for the max N:

```bash
make devspace-deploy-existing-openshift N=4 TYPE=opencode
```

If users are missing, the suite **fails** with an explicit message (it does not create them).

Prefer workspaces already **Running** before the run (cold start adds minutes).

## Run

From the repo root:

```bash
make performance N_LIST=1,2,4
make performance N_LIST=1
```

Optional env:

| Var | Default | Meaning |
|-----|---------|---------|
| `AI_NAMESPACE` | `private-assistant-ai-serving` | AI serving namespace |
| `MODEL_ID` | from LLMInferenceService / chart default | Chat model id |
| `PERF_GATEWAY_MAX_TOKENS` | `128` | Completion cap for gateway stage |
| `PERF_GATEWAY_TIMEOUT` | `180` | Per-request timeout (seconds) |
| `PERF_OPENCODE_TIMEOUT` | `180` | Per-OpenCode agent turn (seconds) |

`N=1` is the single-user baseline row of the same ladder.
