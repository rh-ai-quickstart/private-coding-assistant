---
name: deploy-existing-openshift
description: Deploy the Private AI Coding Assistant (llm-d + vLLM) on an existing OpenShift cluster using Helm. Use when the user wants to deploy, test, or redeploy the AI serving stack on a running cluster.
---

# Deploy on Existing OpenShift

## Prerequisites

Before deploying, confirm these with the user:

1. **Namespace** — ask the user for a suffix. Default prefix is `private-assistant-`. Example: `private-assistant-itay`.
2. **HF_TOKEN** — check if `.env` has `HUGGINGFACE_TOKEN` or `HF_TOKEN`. If neither exists, ask the user to provide one.
3. **Cluster access** — verify `oc whoami` succeeds.

## Deployment Steps

1. Verify cluster connectivity with `oc whoami`.
2. Check GPU nodes are available (`oc get nodes` with GPU capacity).
3. If the namespace already exists, annotate it for Helm adoption:
   ```
   oc annotate namespace <NS> meta.helm.sh/release-name=<NS>-platform-config meta.helm.sh/release-namespace=<NS> --overwrite
   oc label namespace <NS> app.kubernetes.io/managed-by=Helm --overwrite
   ```
4. Run `make deploy NAMESPACE=<NS>`.
5. Wait for the storage-initializer to download the model (~4 min).
6. Wait for vLLM to load model weights into GPU (~3 min).
7. Verify pods are `1/1 Running`: `oc get pods -n <NS>`.
8. Create an OpenShift Route for external access:
   ```
   oc create route passthrough qwen3-coder --service=qwen3-coder-kserve-workload-svc --port=8000 -n <NS>
   ```
9. Test the endpoint: `curl -sk https://<route-host>/v1/models`.

## Summary

The deploy creates:
- A PVC for model cache (100Gi)
- An HF token secret
- An LLMInferenceService (Qwen3-Coder-30B-A3B-Instruct-FP8, 1 GPU)
- A passthrough Route for external HTTPS access

## Teardown

```
make undeploy NAMESPACE=<NS>
oc delete route qwen3-coder -n <NS>
```
