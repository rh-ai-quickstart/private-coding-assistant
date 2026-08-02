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
4. **DevSpaces count (N)** — ask how many demo DevSpaces to create (positive integer). Do **not** invent custom namespaces or `private-assistant-<name>` DevSpace namespaces. Users are always `dev-user1..N` in namespaces `dev-userN-devspaces` (N separate Helm releases; each ns has one DevWorkspace `code-workspace-1`, not `devspaces[0..N-1]` in one release). Demo passwords are `DevN@PCA2026!`.
5. **RHCL (AI Gateway)** — existing OpenShift does not install the RHCL *operator* via make. Confirm `oc get crd authpolicies.kuadrant.io`. The ai-serving chart creates a `Kuadrant` CR in `kuadrant-system` when `aiGateway.kuadrant.create=true` (the default for existing OCP). IDE traffic defaults to `pca-ai-gateway` with per-DevSpaces API keys. llm-d Gateway is annotated `opendatahub.io/managed=false` so ODH does not attach conflicting AuthPolicies.

   **If `kuadrant-system` is already owned by another Helm release** (shared cluster), the install will fail with an ownership conflict. Detect with:
   ```bash
   oc get namespace kuadrant-system -o jsonpath='{.metadata.annotations.meta\.helm\.sh/release-name}' 2>/dev/null
   ```
   If it prints a different release name, add `HELM_ARGS='--set aiGateway.kuadrant.create=false'` to reuse the existing Kuadrant instance:
   ```bash
   make ai-serving-deploy-existing-openshift HELM_ARGS='--set aiGateway.kuadrant.create=false'
   ```

## ARO-specific overrides

On ARO (Azure), the chart defaults use AWS storage/hardware. Add these to `HELM_ARGS` for any ARO deployment:

```bash
HELM_ARGS="--set storage.storageClass=managed-csi \
  --set hardware.instanceTypeLabel=nvidia.com/gpu.product \
  --set hardware.gpuProduct=NVIDIA-H100-NVL \
  --set hardware.cpu.request=8 --set hardware.cpu.limit=16 \
  --set hardware.memory.request=80Gi --set hardware.memory.limit=120Gi \
  --set model.id=Qwen/Qwen3.6-35B-A3B-FP8 \
  --set model.name=qwen36-vllm \
  --set vllm.useCustomRuntime=true \
  --set vllm.image=vllm/vllm-openai:v0.19.0 \
  --set vllm.maxModelLen=262144 \
  --set vllm.toolCallParser=qwen3_xml \
  --set epp.enabled=false \
  --set aiGateway.kuadrant.create=false"
```

Also enable TrustyAI in the DSC before deploying with guardrails (ARO only — RHOAI doesn't enable TrustyAI by default):
```bash
oc patch datasciencecluster default-dsc --type=merge \
  -p '{"spec":{"components":{"trustyai":{"managementState":"Managed"}}}}'
# Wait ~1 min for GuardrailsOrchestrator CRD to appear
oc get crd guardrailsorchestrators.trustyai.opendatahub.io
```

GPU node management (ARO, `aro-pca-aue` cluster):
```bash
# Scale up before testing (H100 node costs money)
oc scale machineset aro-pca-aue-cq6r2-gpu-h100 -n openshift-machine-api --replicas=1
# Scale down when done — CRITICAL
oc scale machineset aro-pca-aue-cq6r2-gpu-h100 -n openshift-machine-api --replicas=0
```

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

### DevSpaces (N demo users)

4. Ask for **N** (how many DevSpaces). Do not ask for custom namespace suffixes.
5. Sync HTPasswd + deploy workspaces:
   ```bash
   make devspace-deploy-existing-openshift N=<n>   # writes values + deploys dev-user1..N
   make setup-idp                                   # applies DevN@PCA2026! into pca-htpasswd
   ```
   Order may be reversed if users already exist; after changing `N`, always re-run `make setup-idp`.
6. Tell the user to log in via **pca-htpasswd** as `dev-user1` / `Dev1@PCA2026!` (etc.), open the Dev Spaces dashboard, start `code-workspace-1`, then open the **opencode-web** endpoint (port 4096). Basic Auth user `opencode`; password from:
   ```bash
   oc get secret opencode-web-password -n dev-user1-devspaces \
     -o jsonpath='{.data.password}' | base64 -d
   ```

Single-user redeploy (same convention):
```bash
make devspace-deploy-existing-openshift DEV_USER=dev-user2
# → namespace defaults to dev-user2-devspaces
```

Optional:
- Default IDE is OpenCode (`TYPE=opencode`). For Continue/Roo/Cline: `TYPE=continue`.
- Optional team attribution: `HELM_ARGS='--set devspaces[0].team=platform'` (sends `X-PCA-Team`).
- With Langfuse enabled, `pca-observability.langfuse.ioCapture` defaults to `full`. Opt out: `--set pca-observability.langfuse.ioCapture=metadata`.

### OpenCode image build (first time)

After the first OpenCode deploy, trigger the custom image build once if needed:

```bash
oc start-build devspaces-opencode -n opencode-build --follow
```

### MCP (optional)

```bash
make ai-serving-deploy-existing-openshift HF_TOKEN=hf_xxx MCP_ENABLED=true
make devspace-deploy-existing-openshift N=<n> MCP_ENABLED=true

# Or toggle after deploy
make mcp-enable AI_NAMESPACE=<AI_NAMESPACE> DEV_USER=dev-user1
make mcp-disable AI_NAMESPACE=<AI_NAMESPACE> DEV_USER=dev-user1
```

> Gateway CRDs (`mcp.kuadrant.io`) are not widely available — `MCP_ENABLED` always sets `pca-mcp.gateway.enabled=false`.

After enabling, tell the developer to run **`Developer: Reload Window`** in VS Code. Verify: `oc get pods -n <AI_NAMESPACE> | grep openshift-mcp`

See `deploy_existing_openshift/README.md` and `pca-platform-config/charts/pca-mcp/README.md`.

### Guardrails (optional)

Guardrails deploy automatically with `ai-serving-deploy-existing-openshift` when `guardrails.enabled: true` is set in `deploy_existing_openshift/values-platform-config.yaml` before deploying.
Guardrails pods: `pca-guardrails-*` (2/2), `prompt-injection-detector-*` (1/1), `guardrails-proxy-*` (1/1).
The proxy forwards `X-PCA-*` identity headers to the orchestrator/LLM.

To route IDE chat through guardrails when deploying DevSpaces:
```
make devspace-deploy-existing-openshift N=<n> \
  HELM_ARGS='--set guardrails.enabled=true --set guardrails.endpoint=http://guardrails-proxy.<AI_NS>.svc.cluster.local:8080'
```
Tab autocomplete stays on the direct llm-d gateway (lower latency, no guardrails needed).

## Teardown

```bash
# Remove one developer's DevSpace
make devspace-undeploy-existing-openshift DEV_USER=dev-user1

# Remove the AI serving stack (removes namespace)
make ai-serving-undeploy-existing-openshift
```

**If the namespace gets stuck terminating**, it is almost always a `GuardrailsOrchestrator` finalizer (`trustyai.opendatahub.io/gorch-finalizer`) blocking deletion. Check and clear it:
```bash
# Confirm the blocker
oc get namespace <NS> -o jsonpath='{.status.conditions[?(@.type=="NamespaceContentRemaining")].message}'

# Remove the finalizer so the namespace can complete termination
oc patch $(oc get guardrailsorchestrators -n <NS> -o name) \
  -n <NS> --type=merge -p '{"metadata":{"finalizers":[]}}'
```
This is safe — the TrustyAI operator has already been notified of deletion; patching the finalizer just unblocks the namespace controller.
