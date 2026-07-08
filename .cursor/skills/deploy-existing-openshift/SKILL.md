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

## Deployment Steps

### AI Serving (once per cluster)

1. If the namespace already exists and everything is deployed, adopt it for Helm:
   ```
   oc annotate namespace <NS> meta.helm.sh/release-name=<NS>-platform-config meta.helm.sh/release-namespace=<NS> --overwrite
   oc label namespace <NS> app.kubernetes.io/managed-by=Helm --overwrite
   ```
2. Run `make ai-serving-deploy-existing-openshift` (uses default `AI_NAMESPACE=private-assistant-ai-serving`).
3. Wait for pods to become `Running`: `oc get pods -n <NS> -w`.

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

## Teardown

```bash
# Remove a developer's devspace
make devspace-undeploy-existing-openshift DEV_NAMESPACE=<DEV_NS>

# Remove the AI serving stack (removes namespace)
make ai-serving-undeploy-existing-openshift
```
