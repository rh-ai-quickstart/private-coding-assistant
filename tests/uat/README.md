# Cluster UAT

User acceptance checks against a provisioned OpenShift PCA stack.
Proves a developer can finish a real coding task in OpenCode.

Separate from `make e2e` (`tests/e2e/`) and `make smoke` (`tests/cluster-smoke/`).

## Prerequisites

- `oc` logged in
- `uv` available (UAT reuses the `tests/e2e` venv)
- OpenCode already deployed in `DEV_USER`-devspaces
  (OpenCode DevWorkspace + `opencode-web-password` Secret). Missing OpenCode is a
  **failure**, not a skip.

## Run

From the repo root:

```bash
make uat DEV_USER=dev-user1
```

## Cases

| Test | What it proves |
|------|----------------|
| `test_uat_developer_completes_coding_task_via_opencode` | A developer can complete a coding task in OpenCode (fixture: add `power`; project tests pass) |

Uses the OpenCode HTTP API with the deployed workspace config. Does not rewrite
`opencode.json` or restart the server.
