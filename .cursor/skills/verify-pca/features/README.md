# PCA verification map

This directory is the maintained source for verifying user-facing behavior of the Private AI Coding Assistant on a live OpenShift cluster. Read this index before driving, then use the matching feature file as the recipe.

## Baseline preconditions

- Host `oc` is logged in (`oc whoami` succeeds). Do not drive from inside the provisioner container.
- If `oc whoami` is `dev-userN` and `dev-userN-devspaces` exists, that is `DEV_USER`. Forbidden on `AI_NAMESPACE` is `MODE=devspace`, not an undeployed stack. Do not ask for cluster-admin solely to rerun IDE chat.
- `AI_NAMESPACE` is the deployed AI serving namespace (`private-assistant-ai-serving` on existing OpenShift; often `ai-serving` on ROSA/ARO) when `MODE=ai`.
- `.cursor/skills/verify-pca/scripts/verify-pca.sh doctor` prints `OK=true`.
- Doctor `IDE_VIA` is the IDE front door. After gateway-first guardrails, chat is `gateway` even when the proxy is deployed. `guardrails` on `IDE_VIA` means a leftover DevSpace still pointed at `guardrails-proxy`.
- Never Helm-install a second stack, undeploy, or scale GPU nodes as part of verification.
- Never drive a namespace doctor did not just confirm (`AI_NAMESPACE` in `MODE=ai`, `DEV_NAMESPACE` in `MODE=devspace`).

## Driving conventions

- Start every recipe from doctor-healthy state unless the feature is an expected skip (resource absent or Forbidden for this user).
- Treat every command as literal. Keep gateway hostnames, secret names, and JSON field names unchanged.
- Default `chat` follows `IDE_VIA` / Forbidden AI ns (OpenCode when that is the user path). Use `VIA=llmd` only when the map says the llm-d escape hatch. Use `VIA=gateway` only when `IDE_VIA=gateway` and `API_KEY_PRESENT=true`.
- Put `DEV_USER=…` on the same command line when doctor did not infer it from `oc whoami`.
- Restore nothing on the cluster after chat (stateless HTTP). `opencode-chat` may leave the workspace Started. Do not delete proof artifacts during cleanup.
- Unique user prompt token `pca-verify-$RUN_ID` so overlapping runs are distinguishable in Langfuse if enabled.

## Proof and skip reporting

- Capture HTTP or OpenCode status plus body (and chat request JSON) under `.cursor/skills/verify-pca/artifacts/$RUN_ID/`.
- Mutation/auth proof includes a second call that shows the opposite case (401 then 200, or block then clean chat).
- Record the feature ID, `VIA`, namespace, `IDE_VIA`, and entry point with every artifact.
- Report an unreachable path with the command run and the unmet precondition (`AI_NAMESPACE_ACCESS=forbidden`, `AI_GATEWAY_PRESENT=false`, no DevWorkspace, Grafana deploy missing).
- Do not report a skipped RHCL path as verified because llm-d or OpenCode chat succeeded.

## Feature entry contract

Each feature file starts with an H1 title and one paragraph describing the user-visible behavior. It then uses exactly four H2 sections in this order.

1. `Sub-features` lists short IDs with one line for each behavior.
2. `How to get to it (user POV)` lists every user entry point.
3. `Driving it with verify-pca` starts with `Preconditions:` and uses labeled bullets that pair each user action with an exact command and observable result.
4. `Gotchas` lists traps that can waste or invalidate a verification run.

Keep implementation details out of the map. Name only user paths, stable handles, required state, commands, and observable proof.

## Features

- [Chat completions](./chat-completions.md) covers IDE-style chat through OpenCode, RHCL, and the llm-d escape hatch.
- [API key auth](./api-key-auth.md) covers missing, invalid, and valid Bearer keys on the RHCL front door.
- [List models](./models-list.md) covers `GET /v1/models` on both gateways.
- [DevSpaces OpenCode](./devspaces-opencode.md) covers workspace reachability and the OpenCode Web entry.
- [Guardrails](./guardrails.md) covers secret-block then clean chat when HTTPRoute sends chat through `guardrails-proxy`.
- [Grafana](./grafana.md) covers the in-cluster health endpoint and the Grafana route.
