# Developer-only cluster smoke tests for Private AI Coding Assistant

Run against an **already provisioned and deployed** OpenShift cluster (existing OpenShift, ROSA, or ARO). Not wired into CI.

## Prerequisites

- `oc` logged in (`oc whoami` succeeds)
- Python 3.11+
- AI serving (and optionally DevSpaces / Langfuse / Guardrails) already deployed

## Quick start

From the repo root:

```bash
# Full suite (existing OpenShift defaults)
make smoke

# ROSA / ARO full-stack namespaces
make smoke AI_NAMESPACE=ai-serving DEV_NAMESPACE=dev1-devspaces

# Single component
make smoke COMPONENT=vllm
make smoke COMPONENT=grafana
make smoke COMPONENT=langfuse
make smoke COMPONENT=otel
make smoke COMPONENT=devspaces DEV_NAMESPACE=private-assistant-itay
make smoke COMPONENT=langfuse DEV_NAMESPACE=private-assistant-itay   # includes DevSpace→Langfuse I/O test when DEV_NAMESPACE set
make smoke COMPONENT=guardrails
make smoke COMPONENT=readiness

# Free-form pytest filter
make smoke PYTEST_ARGS='-k "grafana or readiness"'

# Parallelism (default N=4); serial:
make smoke N=1
```

Or from this directory:

```bash
make smoke AI_NAMESPACE=ai-serving DEV_NAMESPACE=dev1-devspaces
```

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `AI_NAMESPACE` | `private-assistant-ai-serving` | AI serving / observability namespace |
| `DEV_NAMESPACE` | _(empty)_ | DevSpaces namespace; DevSpaces tests skip if unset |
| `COMPONENT` | _(empty)_ | Pytest marker: `readiness`, `vllm`, `grafana`, `langfuse`, `otel`, `devspaces`, `guardrails` |
| `N` | `4` | pytest-xdist workers (`-n`); use `N=1` for serial |
| `PYTEST_ARGS` | _(empty)_ | Extra args passed to pytest |

Optional components (Langfuse, OTel, Guardrails, DevSpaces) **auto-skip** when resources are absent.

## What is checked

1. **readiness** — LLMIS Ready, Gateway Accepted, PVC Bound, predictor pods, optional Grafana/Langfuse/OTel/Guardrails/DevWorkspace
2. **vllm** — `/v1/models`, chat, completions, streaming, tool-calling (with `enable_thinking: false`), workload `/health`
3. **grafana** — route, `/api/health`, Prometheus datasource, dashboard ConfigMaps, Prometheus via `/api/ds/query`
4. **langfuse** — route, health, credentials, project API auth, short-named dependency Services, traces after chat
5. **otel** — deploy Available, health extension
6. **devspaces** — Continue/Roo ConfigMaps, DevWorkspace CR, harness chat with `X-PCA-*` headers
7. **guardrails** — `/healthz`, clean chat, injection block (soft-skip if warn mode)

In-cluster HTTP uses ephemeral `curlimages/curl` pods via `oc run` (gateway is ClusterIP-only).

## Known issues covered by tests

| Symptom | Cause | Fix under test |
|---------|--------|----------------|
| Tool calling fails with raw `<tool_call>` XML in content | Qwen3 thinking mode bypasses structured tool_calls | Request sets `chat_template_kwargs.enable_thinking: false` |
| Grafana Prometheus proxy returns 400 | Thanos namespace tenancy + legacy `/api/datasources/proxy/...` path | Query via Grafana `/api/ds/query` |
| Langfuse CrashLoop; Redis/ClickHouse pods never created | Helm release name too long → Bitnami pod labels > 63 chars | `fullnameOverride: pca-langfuse-*` services must exist |
