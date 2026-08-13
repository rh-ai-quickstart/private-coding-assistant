---
name: connect-devspace
description: >-
  Start a PCA OpenShift DevSpace if needed, fetch its OpenCode Web password and
  route, and connect via oc rsh. Use when the user says connect to devspace-i,
  connect to DevSpace, connect to dev-userN, or wants a shell into a demo
  DevSpace workspace.
---

# Connect to DevSpace

When the user says **connect to devspace-i**, find that user's OpenCode password and connect via `oc rsh`.

## Resolve the user

Map shorthand to OpenShift identity:

| User says | Username | Namespace |
|-----------|----------|-----------|
| `devspace-1`, `dev1`, `dev-user1` | `dev-user1` | `dev-user1-devspaces` |
| `devspace-N`, `devN`, `dev-userN` | `dev-userN` | `dev-userN-devspaces` |

If they give only a number `N`, use `dev-userN` / `dev-userN-devspaces`.
Workspace name is always `code-workspace-1`. Container for shell is `dev-tools`.

## Preferred: run the script

Run on the **host** with `oc` (not inside the project container). Use `oc`, never `kubectl`.

From the repo root (or any cwd; path is absolute to this skill):

```bash
.cursor/skills/connect-devspace/scripts/connect-devspace.sh <N|devN|devspace-N|dev-userN>
```

Examples: `.../connect-devspace.sh 1` or `.../connect-devspace.sh dev-user3`.

On success, the script prints `KEY=value` lines (`NAMESPACE`, `POD`, `OPENCODE_WEB_URL`, `OPENCODE_USER`, `OPENCODE_PASSWORD`, `RSH_CMD`). Use those for the response below. Do **not** run interactive `oc rsh` in the agent shell — give the user `RSH_CMD`.

**If the script fails** (non-zero exit, missing file, or incomplete output), fall back to the manual workflow below and still produce the same response fields.

## Fallback workflow (manual)

1. **Cluster access** — `oc whoami`. If it fails, ask the user to log in.
2. **Confirm workspace exists**
   ```bash
   oc get dw code-workspace-1 -n <username>-devspaces
   ```
3. **Start if Stopped**
   ```bash
   oc patch dw code-workspace-1 -n <username>-devspaces --type merge -p '{"spec":{"started":true}}'
   ```
4. **Wait until Running and pod Ready** (poll every ~5s, up to a few minutes)
   ```bash
   oc get dw code-workspace-1 -n <username>-devspaces -o jsonpath='{.status.phase}{"\n"}'
   oc get pods -n <username>-devspaces
   ```
5. **Fetch OpenCode Web password + route**
   ```bash
   oc get secret opencode-web-password -n <username>-devspaces \
     -o jsonpath='{.data.password}' | base64 -d; echo
   oc get route -n <username>-devspaces | grep opencode-web
   ```
6. **Connect via `oc rsh`**
   ```bash
   POD=$(oc get pods -n <username>-devspaces -o jsonpath='{.items[0].metadata.name}')
   oc rsh -n <username>-devspaces -c dev-tools "$POD"
   ```
   Interactive `oc rsh` needs a real TTY. If the agent shell cannot keep an interactive session, print the exact `oc rsh` command for the user to run in their Cursor terminal, and still report password + Web URL.

## Response to user

Always include:

- Namespace and pod name
- OpenCode Web URL (from the `opencode-web` route)
- HTTP Basic Auth: username `opencode`, password from the secret
- The exact `oc rsh ...` command
- After the `oc rsh` command, tell the user to run `opencode` in that terminal once connected

## Notes

- Do not invent namespaces like `private-assistant-*` for DevSpaces.
- Do not stop other users' workspaces unless asked.
- Do not hardcode passwords in this skill; always read them from the cluster secret at connect time.
