# Performance / scalability ladder

Measures how many developers the stack can serve at once via concurrent OpenCode agents.

> **Do not run** `make performance` alongside root `make performance-vllm` (GuideLLM → live vLLM). Both contend for the same GPU.

## Important limitation

The OpenCode stage is a **load probe**, not a real feature test.

Each agent only creates `MODEL_REGISTRY_TODO.md` (a short TODO list about Model Registry).
It does **not** integrate OpenShift AI Model Registry into the app.
Use this suite for throughput / concurrency metrics only.

## Metrics

All aggregates use **successful (`ok`) workers only**. Rates use **completion / output tokens**.

### Per-worker clocks

| Clock | Meaning |
|-------|---------|
| Worker lifetime | start of setup → worker finished (clone, session, generation) |
| Generation window | first `/event` SSE activity for the session → agent turn returns (tools included) |
| Prefill (TTFT) | prompt HTTP send → first assistant **text** token on `/event` |
| Decode (turn-level) | first assistant text → turn end (may include later tools / model steps; not pure vLLM ITL) |

### Stage columns

| Column | Definition |
|--------|------------|
| `concurrent users (N)` | Planned concurrency |
| `succeeded / failed` | Successful / failed workers |
| `end-to-end output tokens/sec (incl. setup)` | `sum(completion_tokens) / total stage time` |
| `avg / p50 / p95 per-user output tokens/sec (generation only)` | Per-user `completion_i / generation_secs_i`, then mean / percentiles |
| `total stage time (sec)` | `max(worker_end) − min(worker_start)` |
| `active generation window (sec)` | `max(gen_end) − min(gen_start)` |
| `non-generation overhead (sec)` | total stage time − active generation window (clone/setup, etc.) |
| `avg prefill time per user (sec)` | mean of per-user prefill (TTFT) over ok workers |
| `avg decode time per user (sec)` | mean of per-user decode (first text → turn end) over ok workers |
| `total output tokens` | `sum(completion_tokens)` |
| `avg output tokens per user` | mean completion tokens per ok worker |
| `total LLM model calls` | Sum of assistant/model messages with `output tokens > 0` |
| `avg LLM model calls per user` | total LLM model calls / ok |
| `peak GPU utilization (%)` | Peak `nvidia-smi` util over the whole stage (setup + generation) |
| `mean GPU utilization (%)` | Mean `nvidia-smi` util inside the **active generation window** only (`min(gen_start)` → `max(gen_end)`); setup idle is excluded |

### How to read the ladder

As `N` grows:

1. Watch **end-to-end output tokens/sec** — whole-test throughput under concurrency (includes setup).
2. Watch **avg / p95 per-user output tokens/sec** — per-user decode rate fairness under load.
3. Watch **total stage time / overhead / generation window** — whether slowdowns are setup vs generation.
4. Watch **avg prefill / decode time** — TTFT vs post-first-token turn time under load.
5. Watch **LLM model calls** — how deep the agent loop gets (many model steps per user).

## What it does

For each `N` in `N_LIST`:

- Run `N` pre-deployed users (`dev-user1` … `dev-userN`)
- Each clones [multimodal-compliance-monitor](https://github.com/rh-ai-quickstart/multimodal-compliance-monitor)
- Each runs one short agent turn (create `MODEL_REGISTRY_TODO.md`) for load

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
| `MODEL_NAME` | `qwen3-coder` | InferenceService / LLMInferenceService name (`model.name`) for GPU sampling fallback |
| `PERF_OPENCODE_TIMEOUT` | `300` | Per-OpenCode agent turn (seconds) |

`N=1` is the single-user baseline row of the same ladder.
