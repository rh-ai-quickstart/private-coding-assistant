# PCA Deployment — Azure Red Hat OpenShift (ARO)

This folder contains Terraform and GitOps (ArgoCD) artifacts to deploy the
**Private AI Code Assistant** on **Azure Red Hat OpenShift (ARO)** with an
NVIDIA H100 GPU node for LLM inference.

---

## Architecture Overview

```
Developer (DevSpaces / OpenCode)
  │
  │  HTTPS (cluster-internal, self-signed TLS)
  ▼
Data Science Gateway (TLS termination, port 443)
  │  Gateway API + HTTPRoute
  ▼
Envoy Proxy (EPP sidecar, port 8081)
  │  ExtProc → EPP gRPC (port 9002)
  ▼
Endpoint Picker Plugin (EPP)
  │  Selects optimal vLLM replica via:
  │    • Queue depth scoring (weight: 2)
  │    • Prefix cache hit scoring (weight: 3)
  │  Sets x-gateway-destination-endpoint header
  ▼
vLLM Replica N (KServe RawDeployment, port 8000)
  │  Custom ServingRuntime (vLLM v0.19.0)
  │  Tool calling: --enable-auto-tool-choice --tool-call-parser=qwen3_xml
  │  Reasoning:    --reasoning-parser=qwen3
  ▼
Qwen/Qwen3.6-35B-A3B-FP8
  │  FP8 quantized, 35B total / 3B active MoE
  ▼
NVIDIA H100 NVL 94GB HBM3
```

### Scalable Routing Pattern

All client traffic flows through the EPP-based routing stack. The pattern is
designed for multi-replica, multi-GPU scaling:

1. **Data Science Gateway** — TLS termination, stable cluster-internal endpoint
2. **HTTPRoute** — `/v1/chat/completions` and `/v1/completions` route to the EPP
   Envoy proxy; `/v1/models` routes directly to the predictor Service
3. **Envoy + EPP (ExtProc)** — Envoy calls the EPP via gRPC ExtProc. The EPP
   uses the InferencePool to discover all vLLM replicas, scores them by queue
   depth and prefix cache affinity, and sets `x-gateway-destination-endpoint` to
   the optimal pod's IP. Envoy uses ORIGINAL_DST to forward directly.
4. **InferencePool** — selects pods by label (`serving.kserve.io/inferenceservice: qwen36-vllm`)
   and exposes target port 8000. Automatically discovers new replicas.
5. **InferenceModel** — maps model name `Qwen/Qwen3.6-35B-A3B-FP8` to the pool,
   enabling future multi-model routing through a single gateway.

**Current demo: 1 replica.** Scale by increasing GPU nodes and InferenceService
`maxReplicas` — the EPP automatically discovers and routes to new replicas.

---

## Component Versions

### Platform

| Component | Version |
|-----------|---------|
| Azure Red Hat OpenShift (ARO) | 4.20.15 |
| Kubernetes | v1.33.6 |
| RHCOS | 9.6.20260217-1 (Plow) |
| CRI-O | 1.33.9 |

### Operators

| Operator | Version | Channel |
|----------|---------|---------|
| Red Hat OpenShift AI (RHOAI) | 3.3.1 | stable |
| NVIDIA GPU Operator | 26.3.1 | v26.3 |
| Node Feature Discovery (NFD) | 4.20.0 | stable |
| Red Hat DevSpaces | 3.27.1 | stable |
| DevWorkspace Operator | 0.40.1 | fast |
| Red Hat OpenShift GitOps (ArgoCD) | 1.15.4 | latest |
| Red Hat OpenShift Serverless | 1.37.1 | stable |
| Red Hat Service Mesh | 3.3.3 | stable |

### GPU / NVIDIA Stack

| Component | Version |
|-----------|---------|
| NVIDIA Kernel Driver | 550.144.03 |
| CUDA Toolkit (in container) | 12.9 |
| CUDA Compat Libs | 575.57.08 |
| GPU Hardware | NVIDIA H100 NVL 94 GB HBM3 |

> **Driver update note:** If the GPU node is reprovisioned with NVIDIA driver 580+
> (CUDA 13.0), set `VLLM_ENABLE_CUDA_COMPATIBILITY=0` and update `LD_LIBRARY_PATH`
> to remove compat libs. See [Troubleshooting](#troubleshooting).

### AI / ML Stack

| Component | Version | Notes |
|-----------|---------|-------|
| **vLLM** | **0.19.0 (upstream)** | Custom ServingRuntime — see [Why Upstream vLLM](#why-upstream-vllm-v0190) |
| PyTorch | 2.10.0+cu129 | Bundled with vLLM v0.19.0 |
| Transformers | 4.57.6 | Required >=5.1 for Qwen3.6 |
| Model | Qwen/Qwen3.6-35B-A3B-FP8 | 35B total / 3B active MoE, FP8, 256K ctx (native max) |
| Serving | KServe RawDeployment | Via custom ServingRuntime |
| Gateway | Data Science Gateway | Gateway API + HTTPRoute (TLS) |
| EPP | RHOAI odh-llm-d-inference-scheduler | Prefix-cache + queue-depth scoring |
| Envoy Proxy | v1.33.2 (distroless) | ExtProc sidecar for EPP |
| InferencePool | GAIE v1 (GA CRD) | Pod discovery + EPP reference |
| InferenceModel | GAIE v1alpha2 | Model-to-pool mapping |

### IaC / CLI Tools

| Tool | Version |
|------|---------|
| Terraform | 1.9.8 |
| Azure CLI | 2.85.0 |
| oc CLI | 4.21.5 |

---

## Why Upstream vLLM v0.19.0

RHOAI 3.3.1 bundles `registry.redhat.io/rhaiis/vllm-cuda-rhel9` based on vLLM
~0.13 with `transformers <5.x`. The Qwen3.6-35B-A3B-FP8 model uses the
`Qwen3_5MoeForConditionalGeneration` architecture class, which requires:

1. **`transformers >=5.1`** — the tokenizer and config classes for Qwen3.5-MoE
   are not present in older versions
2. **`vLLM >=0.18`** — native support for the Qwen3.5-MoE architecture,
   including DeepGEMM FP8 MoE kernels and FlashAttention v3 on H100
3. **CUDA 12.9 toolkit** — vLLM v0.19.0 ships with PyTorch 2.10 compiled against
   CUDA 12.9. The host NVIDIA driver is 550 (CUDA 12.4), so
   `VLLM_ENABLE_CUDA_COMPATIBILITY=1` bridges the gap using CUDA compat
   libraries (575.57.08)

A **custom `ServingRuntime`** (`vllm-cuda-v0190`) is registered in RHOAI to
serve the model through the standard KServe RawDeployment path, making the
model visible and manageable through the OpenShift AI dashboard.

> **Note:** This custom runtime is unsupported by Red Hat. When RHOAI ships with
> vLLM >= 0.19 and transformers >= 5.1, switch back to the bundled runtime.

---

## Model Tool Calling & Reasoning Configuration

Agentic coding tools (OpenCode, Claude Code, Cline) require vLLM to correctly
parse tool calls and reasoning tokens. Misconfiguration causes `</think>` token
leaks in output and silently dropped tool calls.

### Parser Configuration per Model Family

| Model Family | `--tool-call-parser` | `--reasoning-parser` | Min vLLM | Notes |
|---|---|---|---|---|
| **Qwen3.6 / Qwen3.5 (MoE)** | `qwen3_xml` | `qwen3` | 0.19.0 | XML tool calls + `<think>` blocks |
| Qwen2.5 | `hermes` | _(none)_ | 0.13+ | Hermes JSON format, no thinking mode |
| DeepSeek R1 / V3 | `hermes` | `deepseek_r1` | 0.18+ | JSON tool calls + `<think>` blocks |
| Llama 3.x (Instruct) | `llama3_json` | _(none)_ | 0.15+ | Native JSON tool calling |
| Mistral / Mixtral | `mistral` | _(none)_ | 0.14+ | Mistral tool call format |

### Critical Rules

1. **Never use `--tool-call-parser=hermes` with Qwen3.x** — Hermes expects JSON
   tool calls; Qwen3.x emits XML `<tool_call>` tags. The parser silently fails
   and `</think>` tokens leak into the `content` field.

2. **Always set `--reasoning-parser` for thinking models** — Without it, vLLM
   has no way to separate `<think>...</think>` from content. The raw tokens
   appear in the response and break downstream tool-call parsing in clients.

3. **Use `tool_choice: "auto"` in client requests** — The `"required"` path in
   vLLM uses `TypeAdapter(list[FunctionDefinition]).validate_json()` which only
   handles JSON. Qwen3.x XML tool calls silently fail with `tool_calls: []`.

4. **Avoid `--tool-call-parser=qwen3_coder` with streaming** — Known bug in
   vLLM 0.19.x where the streaming extractor fails across the `</think>` →
   `<tool_call>` boundary. Fixed in 0.20+. Use `qwen3_xml` instead.

### Terraform Variables

The parser configuration is exposed as Terraform variables for easy model swaps:

```hcl
variable "vllm_tool_call_parser" { default = "qwen3_xml" }
variable "vllm_reasoning_parser" { default = "qwen3" }
variable "model_id"              { default = "Qwen/Qwen3.6-35B-A3B-FP8" }
```

### Verifying Tool Calling Works

After deployment, run the smoke test from inside the cluster:

```bash
curl -sk $GATEWAY_URL/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3.6-35B-A3B-FP8",
    "messages": [{"role":"user","content":"List files in /tmp"}],
    "tools": [{"type":"function","function":{"name":"list_files","description":"List directory","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}}],
    "tool_choice": "auto",
    "max_tokens": 200
  }'
```

**Expected:** Response has `"finish_reason": "tool_calls"` with a populated
`tool_calls` array and reasoning in the `reasoning` field (not in `content`).

**Failure indicators:**
- `</think>` appearing in `content` → missing `--reasoning-parser`
- `tool_calls: []` with XML in `content` → wrong `--tool-call-parser`
- `tool_calls: []` silently → using `tool_choice: "required"` (switch to `"auto"`)

---

## Prerequisites

### Tools Required

| Tool | Version | Purpose |
|------|---------|---------|
| `terraform` | >= 1.4.6 | Infrastructure provisioning |
| `az` (Azure CLI) | >= 2.50 | Azure authentication and ARO management |
| `oc` (OpenShift CLI) | >= 4.19 | Cluster interaction and GitOps bootstrap |
| `jq` | >= 1.6 | JSON processing in the GPU MachineSet script |

### Azure Permissions Required

Your Azure account needs:

- **Contributor** or **Owner** on the target subscription
- **User Access Administrator** (for role assignments created by `az aro create`)

Register the ARO resource providers if not already registered:

```bash
az provider register --namespace Microsoft.RedHatOpenShift --wait
az provider register --namespace Microsoft.Compute --wait
az provider register --namespace Microsoft.Storage --wait
az provider register --namespace Microsoft.Authorization --wait
```

### GPU Quota

Request quota for `Standard_NC40ads_H100_v5` in your target region **before**
deployment. The H100 VM requires 40 vCPUs.

```bash
az vm list-usage --location australiaeast -o table | grep -i "NC40ads"
```

### Red Hat Prerequisites

- A **Red Hat account** with an active OpenShift subscription
- **Pull secret** from [console.redhat.com/openshift/install/pull-secret](https://console.redhat.com/openshift/install/pull-secret)

---

## Cluster Specifications

| Component | Specification |
|-----------|--------------|
| Platform | Azure Red Hat OpenShift (ARO) |
| OpenShift version | 4.20.15 |
| Azure region | Australia East (`australiaeast`) |
| Master nodes | 3x `Standard_D8s_v5` |
| Worker nodes | 3x `Standard_D8s_v5` |
| GPU nodes | 1x `Standard_NC40ads_H100_v5` (NVIDIA H100 NVL 94 GB) |
| Storage class | `managed-csi` (Azure Managed Disk CSI) |

---

## Deployment Steps

### Step 1: Authenticate with Azure

```bash
az login
az account set --subscription "<your-subscription-id>"
```

### Step 2: Configure Terraform Variables

```bash
cd PCA_Deployment_ARO/terraform/
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:

| Variable | Description |
|----------|-------------|
| `subscription_id` | Your Azure subscription ID |
| `pull_secret` | Red Hat pull secret (single-line JSON string) |
| `cluster_name` | Cluster name (default: `aro-pca-aue`) |
| `location` | Azure region (default: `australiaeast`) |
| `gitops_repo_url` | Your fork of the `Private_AI_Coding_Assistant` repo |

### Step 3: Deploy Infrastructure with Terraform

```bash
terraform init
terraform plan -out=aro-plan.tfplan
terraform apply aro-plan.tfplan
```

Terraform provisions: Resource Group, VNet, Subnets, ARO Cluster (~35-45 min),
GPU MachineSet, OpenShift GitOps, and ArgoCD App-of-Apps.

### Step 4: Retrieve Cluster Credentials

```bash
az aro list-credentials --name aro-pca-aue --resource-group aro-pca-aue-rg
az aro show --name aro-pca-aue --resource-group aro-pca-aue-rg --query consoleProfile.url -o tsv
oc login <API_URL> --username=kubeadmin --password=<PASSWORD>
```

### Step 5: Set Up DevSpaces Users

After the stack is deployed and the model is serving, create HTPasswd users
and their DevWorkspaces. The script handles OAuth setup, namespace discovery,
and workspace creation as each user (required for dashboard visibility).

```bash
export KUBEADMIN_PASS="<kubeadmin password>"
./scripts/setup-devspaces-users.sh
```

> Edit the `USERS` array inside the script to add/remove developers.

**Alternative: Factory URL (self-service).** Users can also create their own
workspace by navigating to the DevSpaces factory URL — no admin script needed:

```
https://<devspaces-url>/#https://github.com/manujoy7/Private_AI_Coding_Assistant.git
```

DevSpaces reads `devfile.yaml` from the repo root, provisions the workspace
with all pre-configured settings (custom image, env vars, OpenCode extension,
Web UI), and the Devfile tab in the dashboard shows the full devfile content.
This is the recommended enterprise approach for self-service onboarding.

### Step 6: Verify Deployment

```bash
# Check all operators
oc get csv -A | grep -v Succeeded

# Check GPU node
oc get nodes -l nvidia.com/gpu.present=true

# Check model serving
oc get inferenceservice -n ai-serving
oc get servingruntime -n ai-serving

# Check AI Gateway
oc get gateway,httproute -n ai-serving

# Check DevSpaces — workspaces are in auto-provisioned namespaces
oc get devworkspace -A

# Test the model via AI Gateway
GATEWAY_SVC="llm-d-gateway-data-science-gateway-class.ai-serving.svc.cluster.local"
curl -sk https://${GATEWAY_SVC}/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3.6-35B-A3B-FP8",
    "messages": [{"role": "user", "content": "Write a Python hello world"}],
    "max_tokens": 100
  }'
```

---

## GitOps Structure

ArgoCD manages the platform in five sync waves:

```
PCA_Deployment_ARO/
├── terraform/                  # Azure infrastructure
│   ├── main.tf                 # RG, VNet, subnets, ARO cluster, GPU MachineSet
│   ├── gitops-bootstrap.tf     # OpenShift GitOps operator + App-of-Apps
│   ├── variables.tf            # Input variables with defaults
│   ├── versions.tf             # Provider versions
│   ├── outputs.tf              # Credential retrieval commands
│   └── terraform.tfvars.example
├── argocd/
│   ├── 00-app-of-apps.yaml            # Root ArgoCD application
│   ├── 01-operators/                   # Wave 1: Operator subscriptions
│   │   ├── subscriptions.yaml          #   RHOAI, Service Mesh, Serverless, GPU Op, DevSpaces
│   │   ├── nvidia-cluster-policy.yaml  #   GPU Operator ClusterPolicy
│   │   ├── leader-worker-set.yaml      #   LWS controller (llm-d dependency)
│   │   ├── lws-operator-cr.yaml        #   LWS operator instance
│   │   └── cert-manager.yaml           #   cert-manager (llm-d dependency)
│   ├── 02-platform-config/             # Wave 2: Platform configuration
│   │   ├── namespaces.yaml             #   ai-serving, dev1/2/3-devspaces
│   │   ├── datasciencecluster.yaml     #   DSC with KServe Managed mode
│   │   ├── checluster.yaml             #   DevSpaces CheCluster instance
│   │   ├── hf-token-placeholder.yaml   #   HuggingFace token secret
│   │   └── rbac.yaml                   #   RoleBindings for dev users
│   ├── 03-ai-serving/                  # Wave 3: AI serving stack
│   │   ├── llminferenceservice.yaml    #   HardwareProfile + ServingRuntime +
│   │   │                               #   InferenceService (KServe RawDeployment)
│   │   ├── llm-d-gateway.yaml          #   Gateway API Gateway + HTTPRoute
│   │   ├── llm-d-epp.yaml             #   EPP Deployment + Envoy sidecar +
│   │   │                               #   RBAC + ConfigMaps (scheduler config)
│   │   ├── inference-routing.yaml      #   InferencePool + InferenceModel
│   │   ├── pvcs.yaml                   #   100Gi model cache PVC (managed-csi)
│   │   └── tls-secret-job.yaml         #   Self-signed TLS cert for gateway
│   ├── 04-devspaces/                   # Wave 4: Developer workspaces
│   │   ├── devworkspaces.yaml          #   DevWorkspace TEMPLATE (not ArgoCD-managed)
│   │   ├── opencode-image-build.yaml   #   BuildConfig + RBAC for custom image
│   │   ├── devspaces-dashboard-samples.yaml  #   Dashboard landing page samples
│   │   ├── vscode-extensions-config.yaml #   VS Code extension recommendations (sidebar hint only)
│   │   └── roo-code-configmaps.yaml    #   Roo Code provider config
│   └── 05-benchmarks/                  # Wave 5: Performance benchmarks
│       └── guidellm-sweep.yaml         #   GuideLLM sweep job
└── scripts/
    ├── create-gpu-machineset.sh        # Post-cluster H100 node provisioning
    ├── deploy-full-stack.sh            # Full stack deployment script
    ├── post-terraform-fullstack.sh     # Post-terraform automation
    ├── setup-devspaces-users.sh        # HTPasswd IDP + DevWorkspace provisioning
    └── validate.sh                     # Post-deployment validation
```

---

## Key Deployment Artifacts

### HardwareProfile (`nvidia-h100-gpu`)

Registered in `redhat-ods-applications`, makes the H100 GPU visible in the
RHOAI dashboard when deploying models. Defines CPU (4-16), Memory (40-120Gi),
and GPU (1x `nvidia.com/gpu`) resource bounds.

### Custom ServingRuntime (`vllm-cuda-v0190`)

| Field | Value |
|-------|-------|
| Image | `vllm/vllm-openai:v0.19.0` |
| Entrypoint | `python3 -m vllm.entrypoints.openai.api_server` |
| Model format | vLLM |
| Protocol | REST (OpenAI-compatible) |
| CUDA compat | `VLLM_ENABLE_CUDA_COMPATIBILITY=1` + `LD_LIBRARY_PATH` |
| Cache | PVC-backed (`/model-cache`) for persistent model weights and JIT kernels |
| Probes | Startup: 60min tolerance, Readiness: 10s, Liveness: 30s |

**vLLM server args:**

| Arg | Purpose |
|-----|---------|
| `--port=8000` | HTTP listen port |
| `--served-model-name=Qwen/Qwen3.6-35B-A3B-FP8` | Model name in OpenAI API responses |
| `--trust-remote-code` | Required for Qwen3.5-MoE architecture |
| `--enable-prefix-caching` | KV cache reuse for shared prefixes (EPP affinity) |
| `--enable-auto-tool-choice` | Allow model to decide when to use tools (required by OpenCode/Roo Code) |
| `--tool-call-parser=hermes` | Parse Hermes-format tool calls from model output into OpenAI `tool_calls` |

Environment variables handle non-root container constraints:

| Variable | Value | Purpose |
|----------|-------|---------|
| `HF_HOME` | `/model-cache` | HuggingFace cache on PVC |
| `TRITON_CACHE_DIR` | `/model-cache/triton-cache` | Triton MoE kernel cache on PVC |
| `XDG_CACHE_HOME` | `/model-cache/xdg-cache` | General cache on PVC |
| `HOME` | `/tmp` | Writable home for non-root user |
| `VLLM_ENABLE_CUDA_COMPATIBILITY` | `0` | Disabled — host driver 580 (CUDA 13.0) natively supports CUDA 12.9 toolkit |
| `LD_LIBRARY_PATH` | `/usr/local/cuda/lib64:/usr/lib64` | Standard CUDA library paths (no compat libs needed with driver 580) |
| `DG_JIT_CACHE_DIR` | `/model-cache/deep-gemm` | DeepGEMM MoE kernel JIT cache on PVC — saves ~5 min on restart |
| `VLLM_CACHE_ROOT` | `/model-cache/vllm-cache` | torch.compile AOT cache on PVC — saves ~30s on restart |

### InferenceService (`qwen36-vllm`)

- **Mode**: KServe RawDeployment (no Knative/Serverless dependency)
- **Runtime**: `vllm-cuda-v0190`
- **Model args**: `--model=Qwen/Qwen3.6-35B-A3B-FP8 --tensor-parallel-size=1 --max-model-len=262144`
- **Resources per replica**: 8-16 CPU, 80-120Gi RAM, 1x NVIDIA GPU
- **Toleration**: `nvidia.com/gpu=present:NoSchedule`
- **Scaling**: `minReplicas: 1`, `maxReplicas: 4` (increase for more GPU nodes)

**Combined vLLM args** (ServingRuntime + InferenceService):

```
python3 -m vllm.entrypoints.openai.api_server \
  --port=8000 \
  --served-model-name=Qwen/Qwen3.6-35B-A3B-FP8 \
  --trust-remote-code \
  --enable-prefix-caching \
  --enable-auto-tool-choice \
  --tool-call-parser=hermes \
  --model=Qwen/Qwen3.6-35B-A3B-FP8 \
  --tensor-parallel-size=1 \
  --max-model-len=262144
```

> **Tool calling is required** for OpenCode's agentic features. Without
> `--enable-auto-tool-choice` and `--tool-call-parser=hermes`, OpenCode
> requests fail with: `"auto" tool choice requires --enable-auto-tool-choice
> and --tool-call-parser to be set`.

### Model Cache PVC (`model-cache`)

100Gi `managed-csi` PVC stores HuggingFace model weights (~35GB), Triton JIT
kernels, DeepGEMM warmup artifacts (`DG_JIT_CACHE_DIR`), and torch.compile AOT
cache (`VLLM_CACHE_ROOT`). Survives pod restarts to avoid re-downloading the
model and re-compiling kernels (~17 min saved on warm restart — from 19.5 min
→ 2.5 min cold start with populated caches).

### AI Gateway (`llm-d-gateway`)

Gateway API `Gateway` with HTTPS listener (self-signed TLS) and `HTTPRoute`.
Inference requests (`/v1/chat/completions`, `/v1/completions`, `/v1`) route
through the EPP Envoy proxy for intelligent scheduling. Metadata requests
(`/v1/models`) bypass EPP and go directly to the predictor Service.

**Cluster-internal endpoint:**
```
https://llm-d-gateway-data-science-gateway-class.ai-serving.svc.cluster.local/v1
```

### Endpoint Picker Plugin (EPP)

The EPP is the intelligent request scheduler deployed as an Envoy sidecar.

| Component | Image |
|-----------|-------|
| EPP | `registry.redhat.io/rhoai/odh-llm-d-inference-scheduler-rhel9` (RHOAI-bundled) |
| Envoy | `envoyproxy/envoy:distroless-v1.33.2` |

**Scheduling algorithm** (configurable via `EndpointPickerConfig`):
- `queue-scorer` (weight 2) — routes to replicas with shorter queues
- `prefix-cache-scorer` (weight 3) — routes similar prompts to the same replica
  for KV cache reuse, minimizing redundant computation

**ExtProc flow:**
1. Envoy receives the inference request on port 8081
2. Envoy calls EPP via gRPC ExtProc (localhost:9002)
3. EPP queries InferencePool for available vLLM pods
4. EPP scores each pod using queue depth + prefix cache hit metrics
5. EPP returns `x-gateway-destination-endpoint` header with optimal pod IP
6. Envoy forwards request to the selected pod using ORIGINAL_DST cluster

### InferencePool (`qwen36-vllm-pool`)

Selects vLLM predictor pods by label `serving.kserve.io/inferenceservice: qwen36-vllm`
and forwards traffic to port 8000. Automatically discovers new replicas when
InferenceService scales up.

### InferenceModel (`qwen36-model`)

Maps model name `Qwen/Qwen3.6-35B-A3B-FP8` to `qwen36-vllm-pool`. For
multi-model setups, create additional InferenceModel resources pointing to
different InferencePools.

---

## DevSpaces + OpenCode

Each developer workspace runs VS Code in the browser with OpenCode pre-configured
to use the private Qwen3.6 model through the AI Gateway. Two access modes are
available — both are enabled for every workspace:

### OpenCode Access Modes

| Mode | How to Access | Description |
|------|---------------|-------------|
| **VS Code Extension** | `Ctrl+Esc` in editor | Opens OpenCode TUI in a split terminal panel. Context-aware — shares current editor selection. File reference shortcut: `Alt+Ctrl+K`. Extension `sst-dev.opencode` auto-installed via `DEFAULT_EXTENSIONS` env var (official CheCode mechanism — `.vsix` downloaded in `postStart`, then installed by the editor at startup). |
| **Browser Web UI (in-IDE)** | VS Code: `F1` → "Simple Browser: Show" → `http://localhost:4096` | Opens the full OpenCode Web UI inside a VS Code editor tab. **Recommended** — no routing or auth complexity. |
| **Browser Web UI (external)** | Direct route URL from DevSpaces dashboard | Full graphical web UI in a separate browser tab. Uses a direct OpenShift route (no path-prefix issues). **Do NOT set `OPENCODE_SERVER_PASSWORD`** — it conflicts with the che-gateway OAuth, causing a double-auth loop. |

### User Accounts

Users authenticate via HTPasswd identity provider. Accounts are created by the
`scripts/setup-devspaces-users.sh` script.

| User | Dashboard Login |
|------|-----------------|
| `Dev1` | DevSpaces URL with Dev1 credentials |
| `Dev2` | DevSpaces URL with Dev2 credentials |

### DevSpaces Namespace Provisioning (Critical)

DevSpaces auto-provisions a **unique namespace** for each user the first time
they access the dashboard:

```
Pattern: <username>-devspaces-<random-suffix>
Example: Dev1 → dev1-devspaces-wk1ug6
```

**DevWorkspaces CANNOT be pre-deployed into statically-named namespaces via
ArgoCD.** The DevWorkspace controller stamps each workspace with a
`controller.devfile.io/creator` label matching the creating user's UID. The
dashboard only shows workspaces where this label matches the logged-in user.

**Correct workspace creation procedure:**

1. Create users via HTPasswd IDP (handled by `setup-devspaces-users.sh`)
2. Each user logs in (triggers DevSpaces namespace auto-provisioning)
3. The script discovers the auto-provisioned namespace
4. Grants `system:image-puller` RBAC for the custom OpenCode image
5. Logs in as each user via `oc login` and creates the DevWorkspace
   (this sets the `controller.devfile.io/creator` label correctly)

```bash
export KUBEADMIN_PASS="<kubeadmin password>"
./scripts/setup-devspaces-users.sh
```

> **Common mistake:** Creating workspaces as `kubeadmin` in a static namespace
> (e.g., `dev1-devspaces`) results in workspaces that are invisible to the
> target user in the DevSpaces dashboard.

### OpenCode Configuration

| Config | Value |
|--------|-------|
| Provider | OpenAI-compatible (vLLM) |
| Base URL | `https://llm-d-gateway-data-science-gateway-class.ai-serving.svc.cluster.local/v1` |
| Model | `Qwen/Qwen3.6-35B-A3B-FP8` |
| API Key | `EMPTY` (no auth required for cluster-internal traffic) |
| TLS | Self-signed cert (`NODE_TLS_REJECT_UNAUTHORIZED=0`) |
| Extension | `sst-dev.opencode` (auto-installed via `DEFAULT_EXTENSIONS` env var — see [CheCode docs](https://eclipse.dev/che/docs/stable/administration-guide/default-extensions-for-microsoft-visual-studio-code/)) |
| Web UI Port | 4096 (auto-started via `postStart`; access via VS Code Simple Browser at `http://localhost:4096`) |
| Web UI Auth | None — **do NOT set `OPENCODE_SERVER_PASSWORD`** (conflicts with che-gateway OAuth causing double-auth loop) |

### Custom OpenCode Image

The workspace uses a custom container image built from the Red Hat Universal
Developer Image (UDI) with OpenCode pre-installed and pre-configured:

| Component | Detail |
|-----------|--------|
| Base image | `registry.redhat.io/devspaces/udi-rhel8:latest` |
| OpenCode binary | Copied to `/usr/local/bin/opencode` (not symlinked — see troubleshooting) |
| Config | `~/.config/opencode/opencode.json` — points to llm-d gateway |
| Auth | `~/.local/share/opencode/auth.json` — API key `EMPTY` |
| Build namespace | `opencode-build` |
| ImageStream | `devspaces-opencode:latest` |
| Rebuild | `oc start-build devspaces-opencode -n opencode-build` |

> **Important:** The binary is copied to `/usr/local/bin` instead of symlinked
> from `~/.local/bin` because the DevSpaces runtime overlay overwrites the
> latter directory at container start.

---

## Benchmark Results

GuideLLM sweep results for Qwen3.6-35B-A3B-FP8 on H100 NVL:

| Workload | Prompt Tokens | Output Tokens | Peak Throughput (tok/s) | Sync Latency (s) | Sync TTFT (ms) |
|----------|--------------|---------------|----------------------|-------------------|----------------|
| Code Completion | 256 | 128 | 4,512 | 0.70 | 36 |
| Code Generation | 1,024 | 512 | 12,790 | 2.78 | 83 |
| Code Review | 4,096 | 1,024 | 16,133 | 5.59 | 157 |
| File Generation | 8,192 | 2,048 | 13,976 | 11.15 | 208 |

Full results: [`testresults_h100.md`](../testresults_h100.md)

---

## GPU Sizing & TCO

For detailed infrastructure sizing, model comparison, and total cost of ownership
analysis, see [`assets/GPU_Sizing_Considerations_for_AI_Code_Assistant_v3.md`](../assets/GPU_Sizing_Considerations_for_AI_Code_Assistant_v3.md).

**Key findings:**

| Finding | Detail |
|---------|--------|
| **Concurrent users per L40S** | 17 developers at 64K context (Qwen 3.6 35B-A3B) |
| **Cost per developer** | $15–41/mo at 50–500 developers (3yr commitment, ROSA on AWS) |
| **Peak concurrency** | ~20% of team size (65% online × 25% active × 1.2× buffer) |
| **Throughput** | ~42 tok/s per user at 17 concurrent on L40S (exceeds 30 tok/s minimum) |
| **KV cache efficiency** | ~10 KB/token (DeltaNet) vs 48–80 KB/token (standard transformers) |
| **Cold start (warm PVC)** | ~2.5 min with DG_JIT_CACHE_DIR + VLLM_CACHE_ROOT on PVC |
| **Cold start (fresh)** | ~19.5 min (includes HF download + JIT compilation) |

**Recommended GPU tiers:**

- **L40S** (48 GB) — Qwen 3.6 35B-A3B, single-GPU instance, $15–39/dev/mo
- **H100** (80 GB) — Qwen3-Coder-Next 80B, single-GPU instance, $17–52/dev/mo
- **H200** (141 GB) — Large teams (500+) only; AWS requires 8-GPU instances

---

## Scaling

### Scaling GPU Nodes and Model Replicas

The architecture supports scaling from 1 to N replicas. Each replica requires
one H100 GPU node.

```bash
# 1. Scale GPU MachineSet to N nodes
oc scale machineset <infra_id>-gpu-h100 -n openshift-machine-api --replicas=N

# 2. Wait for nodes to be Ready
oc get nodes -l nvidia.com/gpu.present=true -w

# 3. Update InferenceService replicas (maxReplicas already set to 4)
oc patch inferenceservice qwen36-vllm -n ai-serving --type merge \
  -p '{"spec":{"predictor":{"minReplicas": N}}}'

# 4. Verify EPP discovers new replicas (check EPP logs)
oc logs deploy/llm-d-epp -n ai-serving -c epp | grep "Starting refresher"
```

The InferencePool automatically discovers new vLLM pods via label selector.
The EPP immediately starts collecting metrics from new replicas and routes
requests using queue depth + prefix cache scoring.

### Scaling EPP

For very high throughput, scale EPP replicas:

```bash
oc scale deploy/llm-d-epp -n ai-serving --replicas=2
```

### Scale to Zero (stop GPU billing)

```bash
oc patch inferenceservice qwen36-vllm -n ai-serving --type merge \
  -p '{"spec":{"predictor":{"minReplicas": 0}}}'
oc scale machineset <infra_id>-gpu-h100 -n openshift-machine-api --replicas=0
```

### Adding a Second Model

To serve a second model (e.g., a coding-specific model alongside the general one):

1. Create a new `ServingRuntime` and `InferenceService` for the second model
2. Create a new `InferencePool` selecting the second model's pods
3. Create a new `InferenceModel` mapping the model name to the new pool
4. Deploy a second EPP instance pointing to the new pool
5. Add `HTTPRoute` rules to route based on model name header

---

## Destroying the Cluster

```bash
az aro delete --name aro-pca-aue --resource-group aro-pca-aue-rg --yes
az group delete --name aro-pca-aue-rg --yes --no-wait
```

---

## Troubleshooting

**vLLM pod stuck in startup (DeepGEMM warmup):**
First launch compiles ~2,785 DeepGEMM MoE kernels via JIT (~10-15 min).
Subsequent restarts are fast when using PVC-backed cache. The startup probe
allows up to 60 minutes.

**GPU node taint preventing pod scheduling:**
The H100 node has taint `nvidia.com/gpu=present:NoSchedule`. The InferenceService
includes the matching toleration. If deploying custom pods, add the toleration.

**CUDA driver version mismatch:**
If the GPU node has been updated to NVIDIA driver 580+ (CUDA 13.0), set
`VLLM_ENABLE_CUDA_COMPATIBILITY=0` and remove compat libs from `LD_LIBRARY_PATH`
(use `/usr/local/cuda/lib64:/usr/lib64` instead of `/usr/local/cuda/compat:...`).

On original deployments with driver 550 (CUDA 12.4), vLLM v0.19.0 still needs
CUDA 12.9 toolkit support. Set `VLLM_ENABLE_CUDA_COMPATIBILITY=1` and include
the compat libs (575.57.08) in `LD_LIBRARY_PATH`. If you see CUDA errors on
driver 550, verify `LD_LIBRARY_PATH` includes `/usr/local/cuda/compat`.

**AI Gateway returns 503 or 504:**
Check that the EPP pod is Ready (2/2 containers). Check that the InferencePool
has discovered the vLLM pods: `oc logs deploy/llm-d-epp -c epp | grep "Starting refresher"`.
Verify the HTTPRoute backend resolves: `oc get httproute model-route -n ai-serving -o yaml`.

**EPP pod in CrashLoopBackOff:**
Check the EPP config version (`apiVersion: inference.networking.x-k8s.io/v1alpha1`).
Ensure RBAC includes `inferenceobjectives` and `leases`. Check that the
`qwen36-vllm-pool` InferencePool exists.

**OpenCode "auto tool choice requires --enable-auto-tool-choice" error:**
OpenCode sends `tool_choice: "auto"` for agentic features. vLLM rejects these
requests unless both `--enable-auto-tool-choice` and `--tool-call-parser` are set
in the ServingRuntime args. The `hermes` parser works for Qwen3.6 models. To fix:

```bash
oc patch servingruntime vllm-cuda-v0190 -n ai-serving --type='json' -p='[
  {"op": "add", "path": "/spec/containers/0/args/-", "value": "--enable-auto-tool-choice"},
  {"op": "add", "path": "/spec/containers/0/args/-", "value": "--tool-call-parser=hermes"}
]'
```

Then delete the running vLLM pod to trigger a rollout with the new args.

**Model download slow or failing:**
The model-cache PVC persists downloads across restarts. If HuggingFace is rate-limited,
set `HF_TOKEN` in the container environment or the `hf-token` secret.

**OpenCode binary not found in PATH inside DevSpaces workspace:**
The DevSpaces runtime overlay filesystem overwrites `~/.local/bin` at container
start, removing any symlinks placed there during the image build. The fix (already
applied in the Dockerfile) copies the binary to `/usr/local/bin/opencode` instead
of symlinking from `~/.local/bin`. If you still see `opencode: command not found`,
rebuild the image: `oc start-build devspaces-opencode -n opencode-build`.

**DevSpaces dashboard shows 0 workspaces for a user:**
DevSpaces auto-provisions namespaces with a random suffix (e.g.,
`dev1-devspaces-wk1ug6`). The workspace controller sets a
`controller.devfile.io/creator` label to the creating user's UID. The dashboard
only shows workspaces where this label matches the logged-in user. Common causes:

- Workspace was created by `kubeadmin` instead of the actual user
- Workspace is in a statically-named namespace (e.g., `dev1-devspaces`) instead
  of the auto-provisioned one

Fix: Run `scripts/setup-devspaces-users.sh` which logs in as each user and creates
workspaces in the correct namespaces.

**OpenCode VS Code extension not auto-installed:**
The extension is installed via the `DEFAULT_EXTENSIONS` env var — the only reliable
auto-install mechanism in CheCode/DevSpaces. The `postStart` command downloads the
`.vsix` from Open VSX to `/tmp/opencode-ext/`, and the `DEFAULT_EXTENSIONS` env var
tells CheCode to install it at editor startup. Other mechanisms that do NOT work:
- `vscode-extensions-config.yaml` with `recommendations` — only shows the extension
  in the sidebar, does not auto-install
- `che-code.eclipse.org/vscode-extensions` devfile attribute — unreliable, often
  silently ignored by the DevWorkspace controller

If the extension is missing, check: (1) the `postStart` download succeeded
(`ls /tmp/opencode-ext/`), (2) the `DEFAULT_EXTENSIONS` env var is set in the
container, (3) the workspace was fully restarted (not just reconnected). To force
reinstall: delete the workspace and recreate it.

Reference: https://eclipse.dev/che/docs/stable/administration-guide/default-extensions-for-microsoft-visual-studio-code/

**OpenCode Web UI shows blank page or password popup in browser:**
The OpenCode Web UI uses absolute asset paths (`/assets/...`). When served through
the che-gateway path-prefix routing (e.g., `/dev1/opencode-dev1/4096/`), assets
fail to load because the browser resolves them against the domain root. **Do NOT
set `urlRewriteSupported: true`** on the `opencode-web` endpoint — this causes
path-prefix stripping which breaks asset loading.

Additionally, **do NOT set `OPENCODE_SERVER_PASSWORD`** — it causes a double-auth
loop: (1) che-gateway handles OAuth via cookies, then (2) OpenCode demands HTTP
Basic Auth, resulting in a persistent password popup that never resolves.

The correct configuration for the `opencode-web` endpoint:
```yaml
endpoints:
  - name: opencode-web
    targetPort: 4096
    exposure: public
    protocol: https
    attributes:
      cookiesAuthEnabled: true    # boolean true, NOT string "true"
      # NO urlRewriteSupported    # OpenCode doesn't support URL rewriting
# NO OPENCODE_SERVER_PASSWORD env var
```

For in-IDE access (recommended): use VS Code Simple Browser → `http://localhost:4096`.

**OpenCode Web UI (port 4096) not starting automatically:**
The `postStart` command requires the `opencode` binary to be in PATH. If the
image was built with the old symlink approach, the binary won't be found. Rebuild
the image with the `/usr/local/bin` copy fix. To start manually in the meantime:
```bash
export PATH="/home/user/.opencode/bin:$PATH"
nohup opencode web --port 4096 --hostname 0.0.0.0 > /tmp/opencode-web.log 2>&1 &
```
