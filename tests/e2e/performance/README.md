# Performance / scalability ladder

Measures how many developers the stack can serve at once.

## Important limitation

The OpenCode stage is a **load probe**, not a real feature test.

Each agent only creates `MODEL_REGISTRY_TODO.md` (a short TODO about Model Registry).
It does **not** integrate OpenShift AI Model Registry into the app.
Use this suite for throughput / concurrency metrics only.

## Metric: `total_generation/s`

```text
generation_secs (per worker) = first output frame → generation finished
total_generation/s           = total_tokens / generation_secs
```

Stage row with N workers:

```text
total_generation/s = sum(tokens) / sum(generation_secs)
```

**Included in `generation_secs`:** model decode, tool calls/results, further agent turns until the chat/agent turn completes.

**Excluded:** DevWorkspace start, `git clone`, port-forward setup, `/v1/models` probe, session create, health checks.

- **Gateway:** streaming chat; clock starts at the first SSE content chunk.
- **OpenCode:** clock starts at the first `/event` SSE activity frame for the session; ends when the agent turn returns (tools included).

Gateway vs OpenCode workloads still differ in size — compare each stage across N, not gateway tok rate vs OpenCode tok rate as equals.

## What it does

For each `N` in `N_LIST`:

1. **Gateway** — `N` parallel streaming `/v1/chat/completions` through `pca-ai-gateway`
2. **OpenCode** — `N` pre-deployed users (`dev-user1` … `dev-userN`) each clone
   [multimodal-compliance-monitor](https://github.com/rh-ai-quickstart/multimodal-compliance-monitor)
   and run one short agent turn (create `MODEL_REGISTRY_TODO.md`) for load

Prints: `total_generation/s`, tokens, gen secs, ok/fail, GPU % (best effort).

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
