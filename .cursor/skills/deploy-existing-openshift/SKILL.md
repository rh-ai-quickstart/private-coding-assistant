---
name: deploy-existing-openshift
description: Deploy the Private AI Coding Assistant (llm-d + vLLM) on an existing OpenShift cluster using Helm. Use when the user wants to deploy, test, or redeploy the AI serving stack on a running cluster.
---

# Deploy on Existing OpenShift

## Prerequisites

Before deploying, confirm these with the user:

1. **HF_TOKEN** — check if `.env` has `HUGGINGFACE_TOKEN` or `HF_TOKEN`. If neither exists, ask the user to provide one.
2. **Cluster access** — verify `oc whoami` succeeds.
3. **AI serving namespace** — default is `private-assistant-ai-serving`. Inform the user which namespace will be used.
4. **DevSpace namespace** — ask the user what namespace they want for their developer workspace (e.g. `private-assistant-<name>`).

## Deployment Steps

### AI Serving (once per cluster)

1. If the namespace already exists, adopt it for Helm:
   ```
   oc annotate namespace <NS> meta.helm.sh/release-name=<NS>-platform-config meta.helm.sh/release-namespace=<NS> --overwrite
   oc label namespace <NS> app.kubernetes.io/managed-by=Helm --overwrite
   ```
2. If the global ConfigMaps (`continue-config`, `vscode-extensions-config`) already exist in `openshift-devspaces`, adopt them:
   ```
   oc annotate configmap continue-config -n openshift-devspaces meta.helm.sh/release-name=<NS>-platform-config meta.helm.sh/release-namespace=<NS> --overwrite
   oc label configmap continue-config -n openshift-devspaces app.kubernetes.io/managed-by=Helm --overwrite
   oc annotate configmap vscode-extensions-config -n openshift-devspaces meta.helm.sh/release-name=<NS>-platform-config meta.helm.sh/release-namespace=<NS> --overwrite
   oc label configmap vscode-extensions-config -n openshift-devspaces app.kubernetes.io/managed-by=Helm --overwrite
   ```
3. Run `make ai-serving-deploy-existing-openshift NAMESPACE=<NS>`.
4. Wait for pods to become `Running`: `oc get pods -n <NS> -w`.

### DevSpace (per developer)

5. Run `make devspace-deploy-existing-openshift NAMESPACE=<DEV_NS> AI_NAMESPACE=<NS>`.
   - For single-developer (same namespace): just `make devspace-deploy-existing-openshift`.
   - For multi-developer: each dev passes their own `NAMESPACE` and points `AI_NAMESPACE` to the serving namespace.

## Teardown

```bash
# Remove a developer's devspace
make devspace-undeploy-existing-openshift NAMESPACE=<DEV_NS>

# Remove the AI serving stack (removes namespace)
make ai-serving-undeploy-existing-openshift NAMESPACE=<NS>
```
