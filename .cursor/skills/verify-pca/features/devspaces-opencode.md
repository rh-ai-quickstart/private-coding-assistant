# DevSpaces OpenCode

A developer reaches a Dev Spaces workspace and the OpenCode Web UI (port 4096) for that user. Default demo users are `dev-userN` in namespace `dev-userN-devspaces`, workspace `code-workspace-1`.

## Sub-features

- `dw-exists` shows DevWorkspace `code-workspace-1` in the user namespace.
- `opencode-route` shows an `opencode-web` route and a non-empty `opencode-web-password` secret.
- `opencode-chat` (default when proving chat as that user) port-forwards 4096 and sends a short prompt, same as `tests/e2e`.
- `opencode-web` (optional live) opens the Web UI with Basic Auth user `opencode`.
- `opencode-uat` (optional deep) runs the calculator agent path.

## How to get to it (user POV)

- Log in to the cluster as `dev-userN` (demo password from IDP setup, not from this skill), open the Dev Spaces dashboard, start `code-workspace-1`, open the **opencode-web** endpoint.
- Maintainers: `.cursor/skills/connect-devspace/scripts/connect-devspace.sh N` prints `OPENCODE_WEB_URL` and `oc rsh` (and **starts** a Stopped workspace). Prefer `opencode-chat` for API proof so the password stays out of the transcript.

## Driving it with verify-pca

Preconditions:

- `verify-pca.sh doctor` prints `OK=true`. In `MODE=devspace` that only requires this user's DevWorkspace, not AI-namespace reads.
- `DEV_USER` inferred from `oc whoami` or set to an already-deployed demo user. Do not create a new Helm release from this skill.

- **Status only.** Run `.cursor/skills/verify-pca/scripts/verify-pca.sh devspace-status`. Evidence `devspace-status.txt` has `PHASE=`, `OPENCODE_WEB_HOST=` non-empty, `OPENCODE_WEB_PASSWORD_SECRET=true`, `IDE_BASE_URL=`. Do not copy the password into that file.
- **OpenCode chat.** Run `.cursor/skills/verify-pca/scripts/verify-pca.sh opencode-chat`. Starts a Stopped workspace like `ensure_devworkspace_started` in e2e. Observable: `ASSISTANT=` non-empty. Say in proof notes if you started the workspace.
- **Live Web (optional).** Only if proving the UI: run `connect-devspace.sh` for that user, then open `OPENCODE_WEB_URL` with Basic Auth user `opencode` and the secret password. Capture a screenshot or ARIA snapshot that shows OpenCode, not just the route host.
- **Deep agent (optional).** `make uat DEV_USER=<same user>` — OpenCode must already be deployed; missing OpenCode is a failure, not a skip. Use when the change is in the OpenCode image or workspace wiring.
- **Proof.** `dw-exists` + `opencode-route` are the default bar for "workspace is deployed". Chat from IDE is `opencode-chat`, not `devspace-status` alone. If you skip live Web or calculator UAT, say so.

## Gotchas

- `opencode-chat` and `connect-devspace.sh` patch `spec.started: true`. That is expected for this feature, matching e2e. Do not start someone else's workspace.
- Do not invent namespaces like `private-assistant-dev-user1`. Always `<username>-devspaces`.
- Continue workspaces (`TYPE=continue`) have no OpenCode route; report OpenCode unreachable, do not fail the whole stack on that.
- ROSA/ARO may use different usernames than `dev-user1`. Use the namespace that actually exists, or the `oc whoami` user.
- Never put OpenCode or HTPasswd passwords in artifacts.
