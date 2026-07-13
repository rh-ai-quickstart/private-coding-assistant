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
| `make ai-serving-deploy-existing-openshift` | AI serving backend (once per cluster) — namespace, HF token secret, model-cache PVC, LLMInferenceService (Qwen3-Coder-30B via llm-d/vLLM on GPU), Grafana (default on); optional Langfuse + OTel Collector |
| `make devspace-deploy-existing-openshift` | Single developer workspace (per developer) — DevWorkspace with Roo Code, Continue, and Cline pre-configured to hit the cluster-internal llm-d endpoint, plus global DevSpaces ConfigMaps (Continue, VS Code extensions). Roo/Continue/Cline send `X-PCA-*` attribution headers |

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
  HELM_ARGS='--set devspacesGlobalConfig.enabled=false'
```

`ai-serving-deploy-existing-openshift` must run first (creates the AI serving namespace). `devspace-deploy-existing-openshift` requires the DevSpaces operator to be present on the cluster. The first devspace deploy creates global DevSpaces ConfigMaps in `openshift-devspaces`; subsequent deploys should add `--set devspacesGlobalConfig.enabled=false` to avoid Helm ownership conflicts.

### Observability (Grafana + optional Langfuse)

Ships with `pca-ai-serving` via the `pca-observability` subchart:

| Flag | Default | What you get |
|------|---------|--------------|
| `grafana.enabled` | `true` | 1-pod Grafana + boards B/C (latency, KV/GPU). Boards A/D when Langfuse is on |
| `langfuse.enabled` | `false` | Langfuse + OTel Collector; wires vLLM OTLP in the same release |
| `langfuse.ioCapture` | `full` | When Langfuse is on: store full prompt/completion via vLLM middleware (async). Set `metadata` to keep tokens/latency only |

Existing OpenShift uses Prometheus **namespace** tenancy (`:9092`). ROSA full provision uses **cluster** monitoring (`:9091` + `cluster-monitoring-view`).

```bash
# Opt in to Langfuse (full I/O capture is default — keep grafana + pca-observability flags in sync)
make ai-serving-deploy-existing-openshift HF_TOKEN=hf_xxx \
  HELM_ARGS='--set langfuse.enabled=true --set pca-observability.langfuse.enabled=true'

# Routes + secrets
oc get route pca-grafana pca-langfuse -n $AI_NAMESPACE
oc get secret pca-grafana-admin -n $AI_NAMESPACE -o jsonpath='{.data.admin-password}' | base64 -d; echo
oc get secret pca-langfuse-credentials -n $AI_NAMESPACE -o jsonpath='{.data.init-user-password}' | base64 -d; echo
```

**GPU $/hr PLACEHOLDER:** `cost.gpuHourlyUsd: 1.86` is illustrative L40S on-demand from the sizing doc — **not** billing truth. Override per cluster and set `cost.gpuHourlyUsdIsPlaceholder: false`.

**Attribution:** Roo + Continue + Cline send `X-PCA-User` / `X-PCA-DevSpace` / optional `X-PCA-Team` (from `devspaces[].team`). Full prompt/completion bodies go to Langfuse via the vLLM middleware when `ioCapture=full`. See `pca-ai-serving/charts/pca-observability/README.md`.

#### Parameters

| Variable | Default | Used by |
|----------|---------|---------|
| `AI_NAMESPACE` | `private-assistant-ai-serving` | Both targets — the AI serving namespace |
| `DEV_NAMESPACE` | *(required)* | devspace target — the developer's namespace |
| `HF_TOKEN` | from `.env` | ai-serving target — HuggingFace token |

### Cluster smoke tests (developer-only)

After the stack is deployed, verify components against the live cluster (not CI):

```bash
make smoke                                              # full suite
make smoke AI_NAMESPACE=ai-serving DEV_NAMESPACE=dev1-devspaces   # ROSA/ARO
make smoke COMPONENT=vllm                               # one marker
```

Package lives in `tests/cluster-smoke/` (see its README). Optional Langfuse / OTel / Guardrails / DevSpaces checks auto-skip when those resources are absent. Set `DEV_NAMESPACE` for DevSpaces harness tests.

## Directory Structure

```
PCA_Deployment_ROSA/          # Full ROSA (AWS) deployment
├── terraform/                # Cluster provisioning (VPC, ROSA, GPU node pool)
└── charts/
    ├── pca-platform-config/  # Namespace, RBAC, secrets, DSC (+ optional guardrails)
    ├── pca-ai-serving/       # LLMInferenceService, PVC, HardwareProfile, pca-observability
    │   └── charts/pca-observability/  # Grafana + optional Langfuse/OTel Collector
    └── pca-devspaces/        # Per-developer DevWorkspaces + Roo/Continue/Cline ConfigMaps + global DevSpaces config

PCA_Deployment_ARO/           # Full ARO (Azure) deployment
├── terraform/                # Cluster provisioning (VNet, ARO, GPU node pool)
└── charts/

deploy_existing_openshift/    # Helm value overrides (reuses ROSA charts with flags disabled)
├── values-platform-config.yaml   # Disables cluster-scoped resources
├── values-ai-serving.yaml        # Disables cluster-scoped resources; Prometheus namespace mode
└── values-devspaces.yaml         # Single devspace, namespace from Helm release

tests/cluster-smoke/              # Developer-only pytest smoke suite (`make smoke`)
```
