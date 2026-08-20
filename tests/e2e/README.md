# Cluster e2e tests

Long-running end-to-end checks against a provisioned OpenShift PCA stack.
Separate from `make smoke` (`tests/cluster-smoke/`).

## Prerequisites

- `oc` logged in
- `uv` available
- For OpenCode cases: OpenCode must already be deployed in `DEV_USER`-devspaces
  (OpenCode DevWorkspace + `opencode-web-password` Secret). Missing OpenCode is a
  **failure**, not a skip — this suite assumes you intended to run against OpenCode.

## Run

From the repo root:

```bash
make e2e DEV_USER=dev-user1
make e2e DEV_USER=dev-user1 PYTEST_ARGS='-k opencode_calculator'
```

## Cases

| Test | What it proves |
|------|----------------|
| `test_opencode_adds_power_and_unittest_passes` | OpenCode Web API clone + chat adds `power`; `power(2,4)==16` via unittest (uses deployed OpenCode config) |
| `test_opencode_secret_blocked_by_guardrails` | OpenCode chat with fake AWS access key is blocked when chat goes IDE → maas-default-gateway → guardrails-proxy |
| `test_maas_route_class` | From the workspace: chat `/v1`, tab `/local/v1` skips guardrails, `/v1/models` passthrough, SSE TTFB, SR-off still serves local |
| `test_opencode_chat_streams_first_token` | OpenCode `/event` first assistant text arrives before the turn ends |
| `test_is_maas_openai_base_url_accepts_maas_only` / `test_opencode_openai_base_url_is_maas` | IDE URL is MaaS; leftover `pca-ai-gateway` is rejected |
| `test_pca_ai_gateway_absent` | No `Gateway/pca-ai-gateway` |

Guardrails OpenCode case requires:

```bash
# platform (TrustyAI operator via cluster.trustyai)
make ai-serving-deploy-existing-openshift

# IDE still uses maas-default-gateway; HTTPRoute sends /v1/chat/completions to guardrails
make devspace-deploy-existing-openshift DEV_USER=dev-user1 TYPE=opencode \
  HELM_ARGS='--set guardrails.enabled=true'

make e2e DEV_USER=dev-user1 PYTEST_ARGS='-m guardrails'
```

Add new cases as `test_*.py` beside the OpenCode calculator test.

## Performance / scalability

Separate suite under `performance/` (not run by `make e2e`):

```bash
make performance N_LIST=1,2,4
```

OpenCode stage is a short load probe (creates a TODO file), not a real Model
Registry integration. Metrics use `total_generation/s` (generation-only timing).
See [performance/README.md](performance/README.md).
