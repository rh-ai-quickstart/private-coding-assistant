---
name: deploy-existing-openshift
description: Deploy the Private AI Coding Assistant (llm-d + vLLM) on an existing OpenShift cluster using Helm. Use when the user wants to deploy, test, or redeploy the AI serving stack on a running cluster.
---

# Deploy on Existing OpenShift

## Prerequisites

Before deploying, verify these automatically (do NOT ask the user unless something is missing):

1. **HF_TOKEN** — the Makefile reads `HUGGINGFACE_TOKEN` from `.env` automatically. Do NOT read or display `.env` contents (it contains secrets). Just run the make target; if the token is missing, the Makefile will error with a clear message — only then ask the user to provide one.
2. **Cluster access** — run `oc whoami` directly on the host (not inside the container). If it fails, ask the user to log in.
3. **AI serving namespace** — always use `private-assistant-ai-serving` (the default). Do not ask.
4. **DevSpace namespace** — ask the user for a suffix. The namespace will be `private-assistant-<suffix>` (e.g. if the user says "itay", the namespace is `private-assistant-itay`).
5. **RHCL (AI Gateway)** — existing OpenShift does not install the RHCL *operator* via make. Confirm `oc get crd authpolicies.kuadrant.io`. The ai-serving chart creates a `Kuadrant` CR in `kuadrant-system` when `aiGateway.kuadrant.create=true`. IDE traffic defaults to `pca-ai-gateway` with per-DevSpaces API keys. llm-d Gateway is annotated `opendatahub.io/managed=false` so ODH does not attach conflicting AuthPolicies.

## Deployment Steps

### AI Serving (once per cluster)

1. If the namespace already exists and everything is deployed, adopt it for Helm:
   ```
   oc annotate namespace <NS> meta.helm.sh/release-name=<NS>-platform-config meta.helm.sh/release-namespace=<NS> --overwrite
   oc label namespace <NS> app.kubernetes.io/managed-by=Helm --overwrite
   ```
2. Run `make ai-serving-deploy-existing-openshift` (uses default `AI_NAMESPACE=private-assistant-ai-serving`).
3. Wait for pods to become `Running`: `oc get pods -n <NS> -w`.

Grafana (boards B/C) deploys by default. Prometheus uses **namespace** tenancy (`:9092`) via `deploy_existing_openshift/values-ai-serving.yaml`.

Optional Langfuse (traces + boards A/D):
```
make ai-serving-deploy-existing-openshift HF_TOKEN=hf_xxx \
  HELM_ARGS='--set pca-observability.langfuse.enabled=true'
```

Retrieve credentials:
```
oc get secret pca-grafana-admin -n <NS> -o jsonpath='{.data.admin-password}' | base64 -d; echo
oc get route pca-grafana -n <NS>
# Langfuse (if enabled):
oc get secret pca-langfuse-credentials -n <NS> -o jsonpath='{.data.init-user-password}' | base64 -d; echo
oc get route pca-langfuse -n <NS>
```

**GPU $/hr PLACEHOLDER:** default `1.86` is illustrative — not billing truth. Override `pca-observability.cost.gpuHourlyUsd` and set `gpuHourlyUsdIsPlaceholder=false` when you have real rates.

### DevSpace (per developer)

4. If the global ConfigMaps (`continue-config`, `vscode-extensions-config`) already exist in `openshift-devspaces`, adopt them for the first devspace release:
   ```
   oc annotate configmap continue-config -n openshift-devspaces meta.helm.sh/release-name=<DEV_NS>-devspaces meta.helm.sh/release-namespace=<DEV_NS> --overwrite
   oc label configmap continue-config -n openshift-devspaces app.kubernetes.io/managed-by=Helm --overwrite
   oc annotate configmap vscode-extensions-config -n openshift-devspaces meta.helm.sh/release-name=<DEV_NS>-devspaces meta.helm.sh/release-namespace=<DEV_NS> --overwrite
   oc label configmap vscode-extensions-config -n openshift-devspaces app.kubernetes.io/managed-by=Helm --overwrite
   ```
5. Run `make devspace-deploy-existing-openshift DEV_NAMESPACE=<DEV_NS>`.
   - For multi-developer: each dev passes their own `DEV_NAMESPACE`. The first deploy creates global ConfigMaps; subsequent deploys should add `--set devspacesGlobalConfig.enabled=false`.
   - Optional team attribution: `HELM_ARGS='--set devspaces[0].team=platform'` (sends `X-PCA-Team`).
   - Roo + Continue + Cline send `X-PCA-User` / `X-PCA-DevSpace` (and optional `X-PCA-Team`) for Langfuse.
   - With Langfuse enabled, `pca-observability.langfuse.ioCapture` defaults to `full` (vLLM middleware stores prompt/completion bodies asynchronously). Opt out: `--set pca-observability.langfuse.ioCapture=metadata`.

### OpenCode Devspace (per developer, alternative to Continue/Roo/Cline)

OpenCode is a separate workspace type using a custom image with the OpenCode CLI pre-installed and a Web UI on port 4096.

**Deploy (creates namespace, BuildConfig, and DevWorkspace):**
```bash
make devspace-deploy-existing-openshift \
  DEV_NAMESPACE=<username>-devspaces \
  AI_NAMESPACE=<ai-namespace> \
  DEV_USER=<username> \
  TYPE=opencode
```

**First time only — trigger the image build:**
```bash
oc start-build devspaces-opencode -n opencode-build --follow
```

The user starts the workspace from the DevSpaces dashboard. The Web UI is password-protected (HTTP Basic Auth, username: `opencode`). Retrieve the password:
```bash
oc get secret opencode-web-password -n <username>-devspaces \
  -o jsonpath='{.data.password}' | base64 -d
```

### MCP (optional)

```bash
# From the start (combine with Langfuse HELM_ARGS on ai-serving if needed)
make ai-serving-deploy-existing-openshift HF_TOKEN=hf_xxx MCP_ENABLED=true
make devspace-deploy-existing-openshift DEV_NAMESPACE=<DEV_NS> MCP_ENABLED=true

# Or toggle after deploy
make mcp-enable AI_NAMESPACE=<AI_NAMESPACE> DEV_NAMESPACE=<DEV_NS>
make mcp-disable AI_NAMESPACE=<AI_NAMESPACE> DEV_NAMESPACE=<DEV_NS>
```

> Gateway CRDs (`mcp.kuadrant.io`) are not widely available — `MCP_ENABLED` always sets `pca-mcp.gateway.enabled=false`.

After enabling, tell the developer to run **`Developer: Reload Window`** in VS Code. Verify: `oc get pods -n <AI_NAMESPACE> | grep openshift-mcp`

See `deploy_existing_openshift/README.md` and `pca-platform-config/charts/pca-mcp/README.md`.

### Guardrails (optional)

Guardrails deploy automatically with `ai-serving-deploy-existing-openshift` when `guardrails.enabled: true` is set in `deploy_existing_openshift/values-platform-config.yaml` before deploying.
Guardrails pods: `pca-guardrails-*` (2/2), `prompt-injection-detector-*` (1/1), `guardrails-proxy-*` (1/1).
The proxy forwards `X-PCA-*` identity headers to the orchestrator/LLM.

To route IDE chat through guardrails, pass `guardrails.enabled=true` and the proxy endpoint when deploying devspaces:
```
make devspace-deploy-existing-openshift DEV_NAMESPACE=<DEV_NS> \
  HELM_ARGS='--set guardrails.enabled=true --set guardrails.endpoint=http://guardrails-proxy.<AI_NS>.svc.cluster.local:8080'
```
Tab autocomplete stays on the direct llm-d gateway (lower latency, no guardrails needed).

## Teardown

```bash
# Remove a developer's devspace
make devspace-undeploy-existing-openshift DEV_NAMESPACE=<DEV_NS>

# Remove the AI serving stack (removes namespace)
make ai-serving-undeploy-existing-openshift
```
