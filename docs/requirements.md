# Requirements

Summary of what you need before deploying. Path-specific tool and quota details live in the deploy guides.

## Minimum software

| Requirement | Notes |
|-------------|--------|
| OpenShift | 4.20+ (required for Distributed Inference with llm-d GA) |
| Red Hat OpenShift AI (RHOAI) | 3.4 recommended (chart defaults); 3.3 minimum for core llm-d GA |
| OpenShift Dev Spaces | For the IDE workspaces |
| NVIDIA GPU Operator + NFD | GPU node discovery and drivers |
| CLI | `oc`, `helm` v3; ROSA/ARO also need Terraform >= 1.4.6 and cloud CLIs (`aws`/`rosa` or `az`) |
| Hugging Face token | Model download (secret `hf-token` in the AI namespace) |
| Existing OpenShift also | RHCL (Kuadrant) before enabling the AI Gateway — see [deploy_existing_openshift/README.md](../deploy_existing_openshift/README.md) |

## Minimum hardware

| Resource | Guidance |
|----------|----------|
| GPU | One NVIDIA GPU with enough VRAM for the chosen model at FP8 (e.g. L40S 48 GB, A100 80 GB, or H100 NVL). See [benchmarks](benchmarks.md) and [GPU sizing](../assets/GPU_Sizing_Considerations_for_AI_Code_Assistant_v3.md). |
| CPU / memory (workers) | Enough for Dev Spaces workspaces plus platform operators; size per team concurrency |
| Storage | PVC for model cache (typically 50–100+ Gi on the cluster storage class) |

Exact SKUs and quotas:

- ROSA: [PCA_Deployment_ROSA/README.md](../PCA_Deployment_ROSA/README.md) (e.g. `g6e` GPU pool)
- ARO: [PCA_Deployment_ARO/README.md](../PCA_Deployment_ARO/README.md) (GPU MachineSet / family quota)
- Existing cluster: GPU nodes already scheduled and labeled for the GPU Operator

## Permissions

| Path | Typical access |
|------|----------------|
| ROSA / ARO | Cloud admin to create the cluster, then OpenShift `cluster-admin` to install operators and sync GitOps |
| Existing OpenShift | OpenShift `cluster-admin` to deploy AI serving, DevSpaces, and (optional) the demo IDP |

## Accounts and secrets

- Red Hat pull secret / entitlement as required by your OpenShift install path
- Hugging Face token with access to the model you deploy
- Optional: enterprise IDP instead of demo HTPasswd (documented in the existing-OpenShift guide)

## Related

- [Architecture](architecture.md)
- [Deploy from the root README](../README.md#deploy)
