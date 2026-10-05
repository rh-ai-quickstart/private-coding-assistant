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
MaaS / RHCL Gateway (HTTPS + per-namespace API key)
  │  Chat: /v1/chat/completions
  ▼
Guardrails proxy + TrustyAI (enabled by default)
  │  Optional Semantic Router (off in the ARO overlay)
  ▼
llm-d Gateway → workload Service (EPP disabled by default)
  ▼
vLLM Replica N (KServe LLMInferenceService, port 8000 HTTPS)
  │  Upstream vLLM via vllm.image (v0.19.0)
  │  Tool calling: --enable-auto-tool-choice --tool-call-parser=qwen3_xml
  │  Reasoning:    --reasoning-parser=qwen3
  ▼
Qwen/Qwen3.6-35B-A3B-FP8
  │  FP8 quantized, 35B total / 3B active MoE
  ▼
NVIDIA H100 NVL 94GB HBM3
```

### Routing Pattern

The supplied ARO values deploy one vLLM replica with EPP disabled:

1. **MaaS / RHCL** — `maas-default-gateway` authenticates per-namespace API keys.
2. **Chat** — `/v1/chat/completions` goes through guardrails by default, then llm-d. Semantic Router is an optional hop.
3. **Local/non-chat requests** — Continue tab `/local/v1` and other `/v1` paths go to llm-d, skipping guardrails and Semantic Router.
4. **llm-d HTTPRoute** — forwards directly to `qwen3-coder-kserve-workload-svc:8000` (HTTPS).

EPP, InferencePool, and InferenceModel resources render only with `epp.enabled=true`. The current catch-all route still targets the workload Service; enabling those resources does not change its backend.

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
| **vLLM** | **0.19.0 (upstream)** | `vllm.image` on LLMInferenceService — see [Why Upstream vLLM](#why-upstream-vllm-v0190) |
| PyTorch | 2.10.0+cu129 | Bundled with vLLM v0.19.0 |
| Transformers | 4.57.6 | Required >=5.1 for Qwen3.6 |
| Model | Qwen/Qwen3.6-35B-A3B-FP8 | 35B total / 3B active MoE, FP8, 256K ctx (native max) |
| Serving | KServe `LLMInferenceService` | Sole NVIDIA serving path (`vllm.image`) |
| Gateway | Data Science Gateway | Gateway API + HTTPRoute (TLS) |
| EPP | Disabled by default | Optional prefix-cache + queue-depth scorer resources |
| Envoy Proxy | v1.33.2 (distroless) | Optional EPP sidecar; not deployed by default |
| InferencePool | GAIE v1 (GA CRD) | Optional pod discovery + EPP reference |
| InferenceModel | GAIE v1alpha2 | Optional model-to-pool mapping |

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

The chart pins upstream vLLM via **`vllm.image`** on the **`LLMInferenceService`**
(sole NVIDIA serving path). Cluster `enableLLMInferenceServiceTLS=true` is required
so KServe mounts `/var/run/kserve/tls` and the chart’s HTTPS probes / `--ssl-*`
args match.

> **Note:** Upstream `vllm/vllm-openai` is unsupported by Red Hat. When RHOAI
> ships with vLLM >= 0.19 and transformers >= 5.1, point `vllm.image` at the
> bundled runtime image instead.

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

Use Terraform `model_variant` to select a curated model preset:

```hcl
model_variant = "qwen3.6" # or "qwen3.8"
```

Custom model IDs and parsers belong in Helm values: `model.id`, `vllm.toolCallParser`, and `vllm.reasoningParser` on `pca-ai-serving`; keep `modelId` in `pca-devspaces` aligned. The `qwen3.8` preset overrides the model ID and tool parser, so use the default passthrough preset for custom values.

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
| `huggingface_token` | HuggingFace token (required for local Qwen; also required if `semantic_router_enabled = true`) |
| `semantic_router_enabled` | Optional. Leave unset so the ARO overlay keeps SR off. Set `true` only with `huggingface_token` plus extras JSON if you want a split |
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

Configure developer identities in `pca-platform-config`'s `devspaces.instances` and keep usernames/namespaces aligned with `pca-devspaces`'s `devspaces` list. The ARO workspace overlay targets `Dev1` / `dev1-devspaces` and `Dev2` / `dev2-devspaces`. Supply non-empty passwords for the demo HTPasswd IDP, or use your cluster's existing IDP.

Sync the charts, then log in to the DevSpaces dashboard as each user and start the pre-created workspace. Helm renders DevWorkspaces with `started: false`.

**Alternative: Factory URL (self-service).** Users can also create their own
workspace by navigating to the DevSpaces factory URL — no admin script needed:

```
https://<devspaces-url>/#https://github.com/manujoy7/Private_AI_Coding_Assistant.git
```

DevSpaces reads `devfile.yaml` from the repo root. That factory devfile uses direct llm-d access with key `EMPTY`; prefer chart-managed workspaces for MaaS authentication and chat guardrails.

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

# Check DevSpaces — workspaces are in the configured namespaces
oc get devworkspace -A

# Test direct llm-d access (escape hatch; skips MaaS and guardrails)
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

ArgoCD manages the platform using the unified Helm charts at the repo root. Both ROSA and ARO use the same `charts/` directory; ARO-specific overrides are in `values-aro.yaml` within each chart.

```
private-coding-assistant/              ← repo root
├── charts/                            # Unified Helm charts (ROSA + ARO)
│   ├── pca-app-of-apps/               #   Root ArgoCD AppProject + child Applications
│   ├── pca-operators/                 #   Wave 1: Operator Subscriptions
│   │   ├── values.yaml
│   │   └── values-aro.yaml            #   ARO overrides (NFD required, no Serverless)
│   ├── pca-platform-config/           #   Wave 2: Namespace, RBAC, DSC, CheCluster
│   │   ├── values.yaml
│   │   ├── values-aro.yaml            #   ARO overrides (managed-csi storage class)
│   │   └── charts/pca-mcp/           #   Optional: OpenShift MCP server
│   ├── pca-ai-serving/                #   Wave 3: LLMInferenceService, llm-d, MaaS front door
│   │   ├── values.yaml
│   │   ├── values-aro.yaml            #   ARO overrides (model, storage, EPP disabled, …)
│   │   ├── charts/pca-guardrails/     #   TrustyAI guardrails proxy (enabled by default)
│   │   └── charts/pca-observability/ #   Grafana + Langfuse/OTel Collector (enabled on ARO)
│   ├── pca-devspaces/                 #   Wave 4: OpenCode or Continue/Roo/Cline workspaces + API keys
│   │   ├── values.yaml
│   │   └── values-aro.yaml
│   └── pca-benchmarks/               #   Wave 5: GuideLLM sweep (enabled in values-aro.yaml)
│       ├── values.yaml
│       └── values-aro.yaml
│
└── PCA_Deployment_ARO/                ← You are here
    ├── README.md
    ├── Dockerfile.opencode             # Custom OpenCode image with pre-installed CLI
    ├── devfile.yaml                    # DevSpaces factory URL devfile
    ├── terraform/                      # Azure infrastructure provisioning
    │   ├── main.tf                     #   RG, VNet, subnets, ARO cluster, GPU MachineSet
    │   ├── gitops-bootstrap.tf         #   OpenShift GitOps operator + App-of-Apps bootstrap
    │   ├── variables.tf                #   Input variables with defaults
    │   ├── versions.tf                 #   Provider versions
    │   ├── outputs.tf                  #   Credential retrieval commands
    │   └── terraform.tfvars.example
    └── scripts/
        ├── create-gpu-machineset.sh    # Post-cluster H100 node provisioning
        ├── deploy-full-stack.sh        # Full stack deployment script
        ├── post-terraform-fullstack.sh # Post-terraform automation
        ├── setup-devspaces-users.sh    # HTPasswd IDP + DevWorkspace provisioning
        └── validate.sh                 # Post-deployment validation
```

---

## Key Deployment Artifacts

### HardwareProfile (`nvidia-h100-gpu`)

Registered in `redhat-ods-applications`, makes the H100 GPU visible in the
RHOAI dashboard when deploying models. Defines CPU (4-16), Memory (40-120Gi),
and GPU (1x `nvidia.com/gpu`) resource bounds.

### LLMInferenceService (`qwen3-coder`)

| Field | Value |
|-------|-------|
| Image | `vllm/vllm-openai:v0.19.0` (`vllm.image`) |
| Entrypoint | `python3 -m vllm.entrypoints.openai.api_server` |
| Model load | Local PVC path `/model-cache` (storage-initializer; `HF_HUB_OFFLINE=1`) |
| Protocol | HTTPS on :8000 (`--ssl-certfile` / `--ssl-keyfile` under `/var/run/kserve/tls`) |
| Workload Service | `qwen3-coder-kserve-workload-svc:8000` |
| Cache | PVC-backed (`/model-cache`) for model weights and JIT kernels |
| Probes | Startup / readiness / liveness with `scheme: HTTPS` |

**vLLM server args** (from `templates/llminferenceservice.yaml`):

| Arg | Purpose |
|-----|---------|
| `--port=8000` | Listen port |
| `--model=/model-cache` | Local path after storage-initializer |
| `--served-model-name=…` | OpenAI API model name (defaults to `model.id`) |
| `--trust-remote-code` | Required for Qwen3.5-MoE architecture |
| `--enable-prefix-caching` | KV cache reuse for shared prefixes within vLLM |
| `--enable-auto-tool-choice` | Allow model to decide when to use tools (required by OpenCode/Roo Code) |
| `--tool-call-parser=qwen3_xml` | Parse Qwen3.x XML tool calls into OpenAI `tool_calls` |
| `--ssl-certfile` / `--ssl-keyfile` | Serve TLS on :8000 (cluster `enableLLMInferenceServiceTLS=true`) |

Environment variables handle non-root container constraints:

| Variable | Value | Purpose |
|----------|-------|---------|
| `HF_HOME` | `/model-cache` | HuggingFace cache on PVC |
| `HF_HUB_OFFLINE` | `1` | Always on for LLMIS local-path load (storage-initializer populates the PVC) |
| `TRITON_CACHE_DIR` | `/model-cache/triton-cache` | Triton MoE kernel cache on PVC |
| `XDG_CACHE_HOME` | `/model-cache/xdg-cache` | General cache on PVC |
| `HOME` | `/tmp` | Writable home for non-root user |
| `VLLM_ENABLE_CUDA_COMPATIBILITY` | `0` | Disabled — host driver 580 (CUDA 13.0) natively supports CUDA 12.9 toolkit |
| `LD_LIBRARY_PATH` | `/usr/local/cuda/lib64:/usr/lib64` | Standard CUDA library paths (no compat libs needed with driver 580) |
| `DG_JIT_CACHE_DIR` | `/model-cache/deep-gemm` | DeepGEMM MoE kernel JIT cache on PVC — saves ~5 min on restart |
| `VLLM_CACHE_ROOT` | `/model-cache/vllm-cache` | torch.compile AOT cache on PVC — saves ~30s on restart |

- **Mode**: KServe RawDeployment via `LLMInferenceService` (no Knative/Serverless dependency)
- **Resources per replica**: 8-16 CPU, 80-120Gi RAM, 1x NVIDIA GPU
- **Toleration**: `nvidia.com/gpu=present:NoSchedule`
- **Scaling**: `spec.replicas: 1` in the chart (raise for more GPU nodes)

**Combined vLLM args** (chart `command` / `args`):

```
python3 -m vllm.entrypoints.openai.api_server \
  --port=8000 \
  --model=/model-cache \
  --served-model-name=Qwen/Qwen3.6-35B-A3B-FP8 \
  --trust-remote-code \
  --enable-prefix-caching \
  --enable-auto-tool-choice \
  --tool-call-parser=qwen3_xml \
  --reasoning-parser=qwen3 \
  --tensor-parallel-size=1 \
  --max-model-len=32000 \
  --ssl-certfile=/var/run/kserve/tls/tls.crt \
  --ssl-keyfile=/var/run/kserve/tls/tls.key
```

> **Tool calling is required** for OpenCode's agentic features. Without
> `--enable-auto-tool-choice` and `--tool-call-parser`, OpenCode
> requests fail with: `"auto" tool choice requires --enable-auto-tool-choice
> and --tool-call-parser to be set`.

### Model Cache PVC (`model-cache`)

100Gi `managed-csi` PVC stores HuggingFace model weights (~35GB), Triton JIT
kernels, DeepGEMM warmup artifacts (`DG_JIT_CACHE_DIR`), and torch.compile AOT
cache (`VLLM_CACHE_ROOT`). Survives pod restarts to avoid re-downloading the
model and re-compiling kernels (~17 min saved on warm restart — from 19.5 min
→ 2.5 min cold start with populated caches).

`HF_HUB_OFFLINE` is always `1`: the storage-initializer populates the PVC before
vLLM starts, so runtime does not call Hugging Face Hub. Keep the PVC across
upgrades for a warm cache.

### AI Gateway (`llm-d-gateway`)

Gateway API `Gateway` with HTTPS listener (self-signed TLS) and `HTTPRoute`.
The catch-all HTTPRoute forwards requests directly to the LLMIS workload Service. EPP is disabled in the supplied ARO values. IDEs normally reach this gateway through the MaaS front door; direct access is the escape hatch.

**Cluster-internal endpoint:**
```
https://llm-d-gateway-data-science-gateway-class.ai-serving.svc.cluster.local/v1
```

### Endpoint Picker Plugin (EPP)

EPP and its Envoy sidecar are optional chart resources, disabled by default. Their configuration is described below; the current catch-all HTTPRoute targets the workload Service rather than EPP.

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

### InferencePool (`qwen3-coder-inference-pool`)

When `epp.enabled=true`, selects vLLM pods by label `serving.kserve.io/inferenceservice: qwen3-coder`
and forwards traffic to port 8000. Automatically discovers new replicas when
the `LLMInferenceService` scales up.

### InferenceModel (`qwen3-coder-model`)

When `epp.enabled=true`, maps model name `Qwen/Qwen3.6-35B-A3B-FP8` to `qwen3-coder-inference-pool`. This automation deploys only one local model at a time.

---

## DevSpaces + OpenCode

The default OpenCode workspace runs VS Code in the browser with the private model configured through MaaS. OpenCode is available through its VS Code extension and Web UI; `type: continue` provides Continue, Cline, and Roo Code instead.

### OpenCode Access Modes

| Mode | How to Access | Description |
|------|---------------|-------------|
| **VS Code Extension** | `Ctrl+Esc` in editor | Opens OpenCode TUI in a split terminal panel. Context-aware — shares current editor selection. File reference shortcut: `Alt+Ctrl+K`. Extension `sst-dev.opencode` auto-installed via `DEFAULT_EXTENSIONS` env var (official CheCode mechanism — `.vsix` downloaded in `postStart`, then installed by the editor at startup). |
| **Browser Web UI (in-IDE)** | VS Code: `F1` → "Simple Browser: Show" → `http://localhost:4096` | Opens the OpenCode Web UI inside an editor tab; use the workspace's OpenCode password when prompted. |
| **Browser Web UI (external)** | Direct route URL from DevSpaces dashboard | Full Web UI in a separate browser tab. The chart starts it with the password from `opencode-web-password`. |

### User Accounts

Users authenticate through the configured cluster IDP. For demo HTPasswd, configure matching users/passwords in `pca-platform-config` as described in [Step 5](#step-5-set-up-devspaces-users).

| User | Dashboard Login |
|------|-----------------|
| `Dev1` | DevSpaces URL with Dev1 credentials |
| `Dev2` | DevSpaces URL with Dev2 credentials |

### DevSpaces Namespace Provisioning

Helm renders stopped DevWorkspaces in `devspaces[].namespace`. The ARO workspace overlay uses `dev1-devspaces` and `dev2-devspaces`, without random suffixes. Keep the platform namespace/user list aligned with those workspace entries.

Users log in to the dashboard and start their pre-created workspace so the controller can stamp the creator identity. ArgoCD ignores changes to `spec.started`, allowing users to start and stop their workspace.

### OpenCode Configuration

IDEs use MaaS with per-namespace API keys. Direct llm-d access is an escape hatch (`aiGateway.escapeHatchToLlmd=true`).

| Config | Value |
|--------|-------|
| Provider | OpenAI-compatible (vLLM) |
| Base URL | `https://maas-default-gateway-data-science-gateway-class.openshift-ingress.svc.cluster.local/v1` |
| Model | `Qwen/Qwen3.6-35B-A3B-FP8` |
| API Key | Per-namespace key from the `pca-maas-apikey` Secret |
| TLS | Self-signed cert (`NODE_TLS_REJECT_UNAUTHORIZED=0`) |
| Extension | `sst-dev.opencode` (auto-installed via `DEFAULT_EXTENSIONS` env var — see [CheCode docs](https://eclipse.dev/che/docs/stable/administration-guide/default-extensions-for-microsoft-visual-studio-code/)) |
| Web UI Port | 4096 (auto-started via `postStart`; access via VS Code Simple Browser at `http://localhost:4096`) |
| Web UI Auth | Password-protected; startup loads `OPENCODE_SERVER_PASSWORD` from the namespace's `opencode-web-password` Secret |

### Custom OpenCode Image

The workspace uses a custom container image built from the Red Hat Universal
Developer Image (UDI) with OpenCode pre-installed and pre-configured:

| Component | Detail |
|-----------|--------|
| Base image | `registry.redhat.io/devspaces/udi-rhel8:latest` |
| OpenCode binary | Copied to `/usr/local/bin/opencode` (not symlinked — see troubleshooting) |
| Config | `~/.config/opencode/opencode.json` — points to MaaS at workspace startup |
| Auth | `~/.local/share/opencode/auth.json` — bake-time `EMPTY` replaced at startup with the namespace's `pca-maas-apikey` key |
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

Full results: [`testresults_h100.md`](testresults_h100.md) · A100 sweep: [`testresults.md`](testresults.md) · Summary: [`docs/benchmarks.md`](../docs/benchmarks.md)

---

## Key differences from ROSA

| Aspect | ROSA (AWS) | ARO (Azure) |
|--------|------------|-------------|
| GPU VM | e.g. `g6e` (L40S) via RHCS machine pool | GPU MachineSet (e.g. H100 NVL / A100 family) after cluster create |
| Storage class | `gp3-csi` | `managed-csi` |
| Charts | `charts/` + `values-rosa.yaml` | Same `charts/` + `values-aro.yaml` |
| Cloud values | Terraform sets `gitops.cloud=rosa` | Terraform sets `gitops.cloud=aro` |
| NSG / network | AWS security groups | ARO-managed subnets (no customer NSG on master/worker) |
| vLLM image | Chart / RHOAI default path for the ROSA overlay | Upstream vLLM (see [Why Upstream vLLM v0.19.0](#why-upstream-vllm-v0190)) |
| Tool / reasoning parsers | Set in ROSA `values-rosa.yaml` / LLMIS args for the chosen model | See [Model Tool Calling & Reasoning Configuration](#model-tool-calling--reasoning-configuration) (e.g. `qwen3_xml` + `qwen3` for Qwen3.6) |

Azure GPU choice depends on quota and model size (A100 80 GB vs H100 NVL 94 GB). Prefer a SKU with native FP8 and enough VRAM for your context window; see [docs/benchmarks.md](../docs/benchmarks.md).

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

The chart renders one vLLM replica. Additional replicas require GPU capacity and a persisted GitOps change; live patches below are temporary under ArgoCD self-healing.

```bash
# 1. Scale GPU MachineSet to N nodes
oc scale machineset <infra_id>-gpu-h100 -n openshift-machine-api --replicas=N

# 2. Wait for nodes to be Ready
oc get nodes -l nvidia.com/gpu.present=true -w

# 3. Update LLMInferenceService replicas
oc patch llminferenceservice qwen3-coder -n ai-serving --type merge \
  -p '{"spec":{"replicas": N}}'

# 4. Check workload pods (EPP is disabled by default)
oc get pods -n ai-serving -l serving.kserve.io/inferenceservice=qwen3-coder
```

The current route targets the workload Service. EPP resources and scoring are not part of the default deployment.

### Scaling EPP

Only for a custom deployment with EPP enabled and its gateway routing configured:

```bash
oc scale deploy/llm-d-epp -n ai-serving --replicas=2
```

### Scale to Zero (stop GPU billing)

```bash
oc patch llminferenceservice qwen3-coder -n ai-serving --type merge \
  -p '{"spec":{"replicas": 0}}'
oc scale machineset <infra_id>-gpu-h100 -n openshift-machine-api --replicas=0
```

### Switching Local Models

This automation deploys **one local model at a time**. Concurrent local models behind the same AI Gateway are unsupported. Use Terraform `model_variant` (`qwen3.6` or `qwen3.8`) to switch models.

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
The H100 node has taint `nvidia.com/gpu=present:NoSchedule`. The
`LLMInferenceService` includes the matching toleration. If deploying custom
pods, add the toleration.

**CUDA driver version mismatch:**
If the GPU node has been updated to NVIDIA driver 580+ (CUDA 13.0), set
`VLLM_ENABLE_CUDA_COMPATIBILITY=0` and remove compat libs from `LD_LIBRARY_PATH`
(use `/usr/local/cuda/lib64:/usr/lib64` instead of `/usr/local/cuda/compat:...`).

On original deployments with driver 550 (CUDA 12.4), vLLM v0.19.0 still needs
CUDA 12.9 toolkit support. Set `VLLM_ENABLE_CUDA_COMPATIBILITY=1` and include
the compat libs (575.57.08) in `LD_LIBRARY_PATH`. If you see CUDA errors on
driver 550, verify `LD_LIBRARY_PATH` includes `/usr/local/cuda/compat`.

**AI Gateway returns 503 or 504:**
Check the guardrails proxy and vLLM workload pods, then inspect `pca-maas-front-door` and `llm-d-gateway-route` in `ai-serving`. The default deployment has no EPP pod or InferencePool to diagnose.

**EPP pod in CrashLoopBackOff (only when explicitly enabled):**
Check the EPP config version (`apiVersion: inference.networking.x-k8s.io/v1alpha1`).
Ensure RBAC includes `inferenceobjectives` and `leases`. Check that the
`qwen3-coder-inference-pool` InferencePool exists.

**OpenCode "auto tool choice requires --enable-auto-tool-choice" error:**
OpenCode sends `tool_choice: "auto"` for agentic features. vLLM rejects these
requests unless both `--enable-auto-tool-choice` and `--tool-call-parser` are set
in the LLMInferenceService args (`charts/pca-ai-serving/values-aro.yaml` /
`templates/llminferenceservice.yaml`). Use `qwen3_xml` for Qwen3.x models.
Fix via GitOps (preferred) or patch the LLMIS container args, then roll the pod.

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
Check that `devspaces.instances` in platform-config and `devspaces` in the workspace chart agree on the username and namespace. Verify that the DevWorkspace exists there and the user has its RoleBinding. Users should start chart-created workspaces from the dashboard so the controller stamps the correct creator identity.

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

The chart deliberately enables password authentication. Retrieve the namespace's `opencode-web-password` Secret and use that password when prompted; keep the startup command that exports `OPENCODE_SERVER_PASSWORD`.

The correct configuration for the `opencode-web` endpoint:
```yaml
endpoints:
  - name: opencode-web
    targetPort: 4096
    exposure: public
    protocol: https
# postStart loads OPENCODE_SERVER_PASSWORD from opencode-web-password
```

For in-IDE access (recommended): use VS Code Simple Browser → `http://localhost:4096`.

**OpenCode Web UI (port 4096) not starting automatically:**
The `postStart` command requires the `opencode` binary to be in PATH. If the
image was built with the old symlink approach, the binary won't be found. Rebuild
the image with the `/usr/local/bin` copy fix. To start manually in the meantime:
```bash
export PATH="/home/user/.opencode/bin:$PATH"
NS=$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace)
export OPENCODE_SERVER_PASSWORD=$(oc get secret opencode-web-password -n "$NS" \
  -o jsonpath='{.data.password}' | base64 -d)
nohup opencode web --port 4096 --hostname 0.0.0.0 > /tmp/opencode-web.log 2>&1 &
```
