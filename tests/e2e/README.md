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

Add new cases as `test_*.py` beside the OpenCode calculator test.

## Performance / scalability

Separate suite under `performance/` (not run by `make e2e`):

```bash
make performance N_LIST=1,2,4
```

OpenCode stage is a short load probe (creates a TODO file), not a real Model
Registry integration. Metrics use `total_generation/s` (generation-only timing).
See [performance/README.md](performance/README.md).
