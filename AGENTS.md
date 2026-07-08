# Private AI Code Assistant

Deploy a private, self-hosted AI coding assistant on OpenShift so developers each get their own namespace with an AI-powered IDE — no code leaves the cluster.

## Deployment Options

### 1. ROSA / ARO — Full from-scratch deployment

Provisions a new cluster (ROSA on AWS or ARO on Azure) with Terraform, then deploys everything via ArgoCD (GitOps).

```
cd PCA_Deployment_ROSA   # or PCA_Deployment_ARO
# 1. Configure terraform/terraform.tfvars
# 2. terraform init && terraform apply
# 3. oc login to the new cluster
# 4. Bootstrap ArgoCD — ArgoCD syncs all Helm charts automatically
```

### 2. Existing OpenShift — Helm-only onto a running cluster

No infrastructure provisioning. Deploys directly via Helm onto a cluster that already has RHOAI, GPU operator, and DevSpaces installed.

Two separate targets:

| Target | What it deploys |
|--------|----------------|
| `make ai-serving-deploy-existing-openshift` | AI serving backend (once per cluster) — namespace, HF token secret, model-cache PVC, LLMInferenceService (Qwen3-Coder-30B via llm-d/vLLM on GPU) |
| `make devspace-deploy-existing-openshift` | Single developer workspace (per developer) — DevWorkspace with Roo Code, Continue, and Cline pre-configured to hit the cluster-internal llm-d endpoint, plus global DevSpaces ConfigMaps (Continue, VS Code extensions) |

#### Single-developer setup (everything in one namespace)

```bash
# 1. oc login to your cluster
# 2. Set HF_TOKEN in .env or pass it directly
make ai-serving-deploy-existing-openshift HF_TOKEN=hf_xxx
make devspace-deploy-existing-openshift DEV_NAMESPACE=private-assistant-ai-serving
```

#### Multi-developer setup (shared AI serving, separate devspaces)

```bash
# 1. Deploy AI serving once
make ai-serving-deploy-existing-openshift HF_TOKEN=hf_xxx

# 2. Each developer deploys their own workspace pointing to the shared AI serving
make devspace-deploy-existing-openshift DEV_NAMESPACE=itay-devspaces
make devspace-deploy-existing-openshift DEV_NAMESPACE=hadar-devspaces \
  --set devspacesGlobalConfig.enabled=false
```

`ai-serving-deploy-existing-openshift` must run first (creates the AI serving namespace). `devspace-deploy-existing-openshift` requires the DevSpaces operator to be present on the cluster. The first devspace deploy creates global DevSpaces ConfigMaps in `openshift-devspaces`; subsequent deploys should add `--set devspacesGlobalConfig.enabled=false` to avoid Helm ownership conflicts.

#### Parameters

| Variable | Default | Used by |
|----------|---------|---------|
| `AI_NAMESPACE` | `private-assistant-ai-serving` | Both targets — the AI serving namespace |
| `DEV_NAMESPACE` | *(required)* | devspace target — the developer's namespace |
| `HF_TOKEN` | from `.env` | ai-serving target — HuggingFace token |

## Directory Structure

```
PCA_Deployment_ROSA/          # Full ROSA (AWS) deployment
├── terraform/                # Cluster provisioning (VPC, ROSA, GPU node pool)
└── charts/
    ├── pca-platform-config/  # Namespace, RBAC, secrets, DSC
    ├── pca-ai-serving/       # LLMInferenceService, PVC, HardwareProfile
    └── pca-devspaces/        # Per-developer DevWorkspaces + Roo Code ConfigMaps + global DevSpaces config

PCA_Deployment_ARO/           # Full ARO (Azure) deployment
├── terraform/                # Cluster provisioning (VNet, ARO, GPU node pool)
└── charts/

deploy_existing_openshift/    # Helm value overrides (reuses ROSA charts with flags disabled)
├── values-platform-config.yaml   # Disables cluster-scoped resources
├── values-ai-serving.yaml        # Disables cluster-scoped resources
└── values-devspaces.yaml         # Single devspace, namespace from Helm release
```
