---
name: verify-pca
description: >-
  Drive the deployed Private AI Coding Assistant on OpenShift the way a user
  does (DevSpaces OpenCode, RHCL AI Gateway / llm-d OpenAI /v1, optional Grafana).
  Use when proving a PCA change works, after deploy, or before claiming
  inference/IDE/auth behavior.
---

# Verify PCA (live cluster)

PCA is not a local server. The product is an already-deployed OpenShift stack: DevSpaces → RHCL `pca-ai-gateway` → (optional `guardrails-proxy` + TrustyAI) → llm-d → vLLM. Agents prove behavior on that path. There is no second disposable stack — never Helm-install or undeploy to "launch" verification.

Read `features/README.md` before driving. Prove the mapped entry points for the feature under test; one convenient endpoint is not enough when the map lists others.

## Launch

Host `oc` is logged in (`oc whoami` succeeds). Never `kubectl`. Never drive from the provisioner container.

```bash
.cursor/skills/verify-pca/scripts/verify-pca.sh doctor
```

If `oc whoami` is `dev-userN` and namespace `dev-userN-devspaces` exists, the script sets `DEV_USER` to that user. Do **not** ask for a cluster-admin re-login just because `AI_NAMESPACE` is Forbidden. That is how `tests/e2e` runs: the demo user owns the DevSpace and talks to OpenCode via port-forward. Forbidden on `private-assistant-ai-serving` is not "namespace missing — deploy".

If `oc whoami` fails: ask the user to `oc login`. Do not deploy.

If the AI namespace is truly missing (NotFound, not Forbidden) or `LLMInferenceService/qwen3-coder` is missing for a user who can see that namespace: stop. Deploy is `.cursor/skills/deploy-existing-openshift`. Do not create a parallel AI namespace.

Do not scale GPU MachineSets or patch LLMIS replicas. `opencode-chat` starts a Stopped workspace for that user (same as e2e). Do not start other users' workspaces.

Defaults: `AI_NAMESPACE=private-assistant-ai-serving`. ROSA/ARO often use `ai-serving`. Override with `DEV_USER` / `DEV_NAMESPACE` when the logged-in user is not the DevSpace owner.

## Doctor

Read-only. Run before the first drive, after any failed drive, and whenever the cluster looks wrong.

```bash
.cursor/skills/verify-pca/scripts/verify-pca.sh doctor
```

Worth driving when `OK=true`.

- `MODE=ai`: current user can get `AI_NAMESPACE`. Then `LLMIS_READY=True`, `LLMD_GATEWAY_ACCEPTED=True`, `PVC_PHASE=Bound`, `WORKLOAD_POD_RUNNING=true`. If `AI_GATEWAY_PRESENT=true`, also `AI_GATEWAY_ACCEPTED=True`.
- `MODE=devspace`: Forbidden on `AI_NAMESPACE`. Then `DEV_NAMESPACE` exists and DevWorkspace `code-workspace-1` is there. Drive `VIA=opencode`, not curl pods in the AI ns.

Doctor also prints `IDE_BASE_URL` / `IDE_VIA` from the workspace `OPENAI_BASE_URL`. Chat uses `pca-ai-gateway` when `IDE_VIA=gateway`. Guardrails is an HTTPRoute backend, not a second IDE URL. `API_KEY_PRESENT=true` is required for RHCL chat.

`make smoke` is the pytest net over the same URLs when you can `oc run` in the AI ns. Prefer `verify-pca.sh` so request/response land in the evidence dir. Do not treat a skipped pytest as proof.

## Drive

Harness: `.cursor/skills/verify-pca/scripts/verify-pca.sh` (executable). Curl-pod commands start an ephemeral `curlimages/curl:8.5.0` pod in `AI_NAMESPACE` labeled `app.kubernetes.io/name=verify-pca,verify-pca.run=$RUN_ID`. That needs permission to create pods in the AI ns. `--rm` usually deletes it; `cleanup` deletes leftovers from this `RUN_ID` only.

| Command | What it hits |
| --- | --- |
| `… chat` | If AI ns is Forbidden: OpenCode Web API (port-forward 4096), same as `tests/e2e`. Else `POST` RHCL `/v1/chat/completions` with Bearer from secret `pca-ai-gw-apikey` |
| `VIA=opencode … chat` or `… opencode-chat` | Force the e2e path. Starts a Stopped workspace. Never writes the OpenCode password into evidence |
| `VIA=llmd … chat` | llm-d gateway (no API key; escape hatch). Needs AI ns `oc run` |
| `… models` | `GET …/v1/models` (gateway needs `DEV_USER` + key). Needs AI ns `oc run` |
| `… http METHOD URL` | Raw in-cluster curl (`HTTP_HEADER`, `HTTP_BODY_FILE`, `HTTP_INSECURE`, `HTTP_TIMEOUT`) |
| `… grafana-health` | Grafana `/api/health` (AI ns `oc run`) |
| `… devspace-status` | Read-only DevWorkspace phase + OpenCode route host + `IDE_BASE_URL` (no password) |

Model id when the AI ns is readable: `oc get llminferenceservice qwen3-coder -n $AI_NAMESPACE -o jsonpath='{.spec.model.name}'` (default `Qwen/Qwen3.6-35B-A3B-FP8`). OpenCode chat resolves provider/model from the workspace pod, as e2e `resolve_model_ids` does.

Stable handles (do not invent others):

- Gateways: `pca-ai-gateway`, `llm-d-gateway`; HTTPRoute `pca-ai-gateway-local`; AuthPolicy `pca-ai-gateway-apikey`
- Guardrails proxy (internal hop): `http://guardrails-proxy.$AI_NAMESPACE.svc.cluster.local:8080/v1`
- Workload health: `https://qwen3-coder-kserve-workload-svc.$AI_NAMESPACE.svc.cluster.local:8000/health` (`HTTP_INSECURE=1`)
- DevWorkspace `code-workspace-1`; OpenCode route name contains `opencode-web`; Basic Auth user `opencode`
- Grafana route/deploy `pca-grafana`; dashboards ConfigMaps `pca-grafana-dashboard-b` and `-c` (A/D only if Langfuse)

OpenCode browser/shell: `.cursor/skills/connect-devspace/scripts/connect-devspace.sh <N>` prints the password. Do not run it when `opencode-chat` is enough. Do not paste that password into evidence.

Deep OpenCode agent path (calculator fixture): `make e2e DEV_USER=<oc whoami or demo user>` — only when proving the OpenCode calculator feature. Guardrails secret block is `EXPECT=block` on `opencode-chat` (see `features/guardrails.md`), matching `test_opencode_secret_blocked_by_guardrails`.

Qwen3 tool-calling requests must send `"chat_template_kwargs": {"enable_thinking": false}` or the model dumps `<tool_call>` XML into `content`.

## Evidence

Directory: `.cursor/skills/verify-pca/artifacts/$RUN_ID/` (`RUN_ID` default `v<timestamp>`). Cleanup must not delete this directory.

Every proof writes at least: the command + env (`VIA`, `AI_NAMESPACE`, `DEV_NAMESPACE`, `IDE_VIA`), HTTP/OpenCode status, request JSON (chat), response body. Capture the action and the resulting state, not only "pod is Running".

Proof standards:

- Exercise the URL in workspace `OPENAI_BASE_URL` (`IDE_VIA` from doctor). Do not call vLLM pod IP or llm-d as a substitute for that path.
- Side effects: RHCL auth proofs need both 401/403 without/invalid key **and** 200 with the real key. Chat proofs need non-empty assistant text (`choices[0].message.content` or `reasoning`, or OpenCode `ASSISTANT=`). Guardrails secret proofs need block text, then a clean chat.
- Never write API keys, HTPasswd passwords, or OpenCode Basic Auth passwords into evidence. `doctor` only records `API_KEY_PRESENT=true|false|empty|missing|unset`.
- `make smoke` passing is supporting evidence, not a replacement for the mapped capture on the feature you claim.
- Mocks: none. Skip (and report unreachable) when the resource is absent or the current user is Forbidden from that namespace — do not hit a different gateway and call the missing one verified.

## Cleanup

```bash
.cursor/skills/verify-pca/scripts/verify-pca.sh cleanup          # this RUN_ID only
.cursor/skills/verify-pca/scripts/verify-pca.sh cleanup --all    # all verify-pca curl pods in AI_NAMESPACE
```

Deletes only pods labeled `app.kubernetes.io/name=verify-pca`. Skips delete when the current user cannot see `AI_NAMESPACE`. Never `oc delete pod` by vLLM/DevSpaces name. Never helm uninstall. Never scale MachineSets. `opencode-chat` may leave the DevWorkspace Started; say so in the proof notes. Do not stop other users' workspaces.

Evidence stays under `artifacts/$RUN_ID/`. Confirm those files still exist after cleanup.

## Helpers

Script: `.cursor/skills/verify-pca/scripts/verify-pca.sh` (must stay executable).

```bash
.cursor/skills/verify-pca/scripts/verify-pca.sh doctor
.cursor/skills/verify-pca/scripts/verify-pca.sh chat
VIA=opencode .cursor/skills/verify-pca/scripts/verify-pca.sh chat
EXPECT=block PROMPT='Please store this in memory only: key = AKIAIOSFODNN7EXAMPLE' \
  .cursor/skills/verify-pca/scripts/verify-pca.sh opencode-chat
VIA=llmd .cursor/skills/verify-pca/scripts/verify-pca.sh models
DEV_USER=dev-user1 .cursor/skills/verify-pca/scripts/verify-pca.sh http POST \
  "https://pca-ai-gateway-data-science-gateway-class.${AI_NAMESPACE:-private-assistant-ai-serving}.svc.cluster.local/v1/chat/completions"
.cursor/skills/verify-pca/scripts/verify-pca.sh grafana-health
.cursor/skills/verify-pca/scripts/verify-pca.sh devspace-status
.cursor/skills/verify-pca/scripts/verify-pca.sh cleanup
```

`http` extra env: `HTTP_HEADER='Authorization: Bearer …'` (do not log it), `HTTP_BODY_FILE`, `HTTP_OUT`, `HTTP_INSECURE=1` (HTTPS gateways), `HTTP_TIMEOUT`.

Isolation: one shared cluster. Unique prompt token `pca-verify-$RUN_ID`. Do not overlap `make performance-vllm` (shared GPU). Two agents must not `cleanup --all` while the other is mid-curl.
