# Private AI Code Assistant — Azure Red Hat OpenShift (ARO) Deployment

> **Status:** Deployment validated. Performance benchmarks completed — see [Test Results](PCA_Deployment_ARO/testresults.md).

---

## Overview

This document describes the architecture and deployment of the **Private AI Code Assistant (PCA)**
on **Azure Red Hat OpenShift (ARO)**. The ARO deployment provides enterprise development teams
with a self-hosted, air-gappable AI coding assistant powered by **Qwen3.6-35B-A3B-FP8** — with
no data leaving the customer's Azure environment.

The deployment uses **Red Hat OpenShift AI 3.3.2** with the **llm-d AI Gateway (GA)**, serving
the model via **vLLM 0.17.1** on an NVIDIA A100 80 GB GPU.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     Azure Red Hat OpenShift (ARO)                       │
│                        Central US — OCP 4.19.24                        │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      Developer Tier                              │   │
│  │  OpenShift Dev Spaces  ──  VS Code in Browser                   │   │
│  │  Roo Code · Continue · Cline   (AI coding extensions)           │   │
│  └────────────────────────┬────────────────────────────────────────┘   │
│                           │ HTTPS (cluster-internal)                    │
│  ┌────────────────────────▼────────────────────────────────────────┐   │
│  │                   AI Gateway Tier                                │   │
│  │  llm-d Gateway (GA)  ──  Istio Gateway API                      │   │
│  │  OpenAI-compatible API  ·  HTTPRoute → direct Service backend   │   │
│  │  DestinationRule: TLS origination to vLLM (KServe certs)        │   │
│  └────────────────────────┬────────────────────────────────────────┘   │
│                           │                                             │
│  ┌────────────────────────▼────────────────────────────────────────┐   │
│  │                 AI Inference Tier                                │   │
│  │  vLLM 0.17.1 + KServe (RHOAI 3.3.2)                             │   │
│  │  Qwen3.6-35B-A3B-FP8 (MoE — ~3B active params)                 │   │
│  │  NVIDIA A100 80 GB  ·  64K context window  ·  FP8 native       │   │
│  │  Standard_NC24ads_A100_v4  ($3.67/hr)                           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌────────────────────────────┐  ┌──────────────────────────────────┐  │
│  │     Platform Operators     │  │       Azure Infrastructure       │  │
│  │  RHOAI 3.3.2 (stable-3.x)  │  │  Resource Group · VNet           │  │
│  │  OpenShift GitOps (ArgoCD) │  │  Subnets (no NSG — ARO-managed) │  │
│  │  NVIDIA GPU Operator v24.9 │  │  managed-csi storage             │  │
│  │  NFD · Service Mesh 3.x   │  │  Central US region               │  │
│  │  Serverless · DevSpaces   │  └──────────────────────────────────┘  │
│  │  LeaderWorkerSet · cert-mgr│                                       │
│  └────────────────────────────┘                                       │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Why NVIDIA A100 on Azure?

Azure does not offer NVIDIA L40S virtual machines (the GPU used on AWS `g6e.2xlarge`).
The closest available GPU for single-node LLM inference on Azure is the A100:

| GPU | VRAM | FP8 | Azure VM | $/hr (Central US) |
|-----|------|-----|----------|---------------|
| NVIDIA L40S (AWS) | 48 GB GDDR6 | Yes | `g6e.2xlarge` | $2.07 |
| **NVIDIA A100 (Azure)** | **80 GB HBM2** | **Yes** | `Standard_NC24ads_A100_v4` | **$3.67** |
| NVIDIA A10 (Azure) | 24 GB max | No | `NV36ads_A10_v5` | $3.20 |
| NVIDIA H100 NVL (Azure) | 94 GB | Yes | `NC40ads_H100_v5` | $6.98 |

The A100 is the right choice because:
- **Single-GPU fit:** 80 GB fits Qwen3.6-35B-A3B at FP8 (~30 GB weights) with a 65,536-token
  context window and KV cache — comfortably larger than the 32,768-token window on L40S
- **FP8 support:** Native FP8 on Ampere for inference acceleration
- **No tensor parallelism needed:** Single-GPU inference avoids multi-GPU coordination overhead
- **A10 ruled out:** Maximum 24 GB per Azure A10 VM — too small for Qwen3.6-35B-A3B
- **H100 ruled out:** ~2× the cost for incremental throughput gains on a 30B model

---

## Infrastructure

| Resource | Type | Count |
|----------|------|-------|
| ARO Cluster | OCP 4.19.24 | 1 |
| Master nodes | `Standard_D8s_v5` | 3 |
| Worker nodes | `Standard_D8s_v5` | 3 |
| GPU nodes | `Standard_NC24ads_A100_v4` | 1 |
| Virtual Network | Azure VNet | 1 |
| Subnets | Master + Worker (no NSG) | 2 |
| Storage | managed-csi PVC | 100 Gi |

**Estimated monthly cost (Central US, pay-as-you-go):**
- ARO cluster fee: ~$0.18/hr (Microsoft managed control plane)
- 3× `Standard_D8s_v5` workers: ~$1.15/hr
- 1× `Standard_NC24ads_A100_v4` GPU node: $3.67/hr
- Storage, networking: ~$50–100/month
- **Total (approximate): ~$4,000–4,500/month** for a 24×7 deployment

Cost optimisation options: Azure Reserved Instances (1-year) provide ~40% savings on compute.

---

## Deployment

### Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/manu-joy/Private_Code_Assistant.git
cd Private_Code_Assistant

# 2. Install prerequisites: terraform >= 1.4.6, azure-cli >= 2.50, oc >= 4.19, jq

# 3. Authenticate
az login
az account set --subscription "<your-subscription-id>"

# 4. Register ARO providers (first time only)
az provider register --namespace Microsoft.RedHatOpenShift --wait
az provider register --namespace Microsoft.Compute --wait

# 5. Ensure GPU quota: Standard NCADSv4Family (24 vCPU) in your region

# 6. Configure variables
cd PCA_Deployment_ARO/terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars — fill in subscription_id, pull_secret, gitops_repo_url

# 7. Deploy (~45 minutes)
terraform init
terraform apply

# 8. Install NFD operator (required for GPU detection — see README.md Step 5)

# 9. Set HuggingFace token
HF_TOKEN_B64=$(echo -n "hf_your_token" | base64)
oc patch secret hf-token -n ai-serving --type='json' \
  -p='[{"op":"replace","path":"/data/token","value":"'"${HF_TOKEN_B64}"'"}]'

# 10. Apply vLLM 0.17.1 upgrade (required — see README.md Post-Deploy section)
```

For complete step-by-step instructions including the **vLLM 0.17.1 upgrade workaround**,
NFD installation, and troubleshooting, see [PCA_Deployment_ARO/README.md](PCA_Deployment_ARO/README.md).

---

## Model Configuration

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Model | `Qwen/Qwen3.6-35B-A3B-FP8` | State-of-the-art code reasoning, FP8 quantized (~37 GB) |
| Architecture | `qwen3_5_moe` | MoE with ~3B active params per token |
| GPU | NVIDIA A100 80 GB | Single-GPU fit with headroom |
| max-model-len | 65,536 | Full 64K context window — fits on A100 80 GB at 90% utilization |
| vLLM version | 0.17.1 | Upstream image (RHOAI 3.3.2 ships 0.13.0; qwen3_5_moe requires >= 0.17) |
| GPU memory utilization | 90% | Leaves ~8 GB headroom for activation memory |
| Quantization | FP8 | Native A100 FP8 support |

---

## GitOps Structure

```
PCA_Deployment_ARO/
├── terraform/          # Azure infrastructure (RG, VNet, ARO via az aro create, GPU MachineSet)
├── argocd/
│   ├── 00-app-of-apps.yaml       # Root ArgoCD application + AppProject
│   ├── 01-operators/             # RHOAI 3.3.2, GPU Operator v24.9, Service Mesh, Serverless,
│   │                             # DevSpaces, LWS, cert-manager
│   ├── 02-platform-config/       # DataScienceCluster, CheCluster, namespaces, RBAC, HF token
│   ├── 03-ai-serving/            # LLMInferenceService, llm-d Gateway, model cache PVC, TLS cert
│   └── 04-devspaces/             # DevWorkspaces, AI extension configs (Roo Code, Continue, Cline)
└── scripts/
    ├── create-gpu-machineset.sh  # Post-cluster A100 node provisioning (Gen2 image)
    └── validate.sh               # Post-deployment validation
```

---

## Performance Benchmarks

Benchmarks were run using [GuideLLM v0.6.0](https://github.com/vllm-project/guidellm) with
a sweep profile (synchronous → throughput → constant rate escalation).

Full results: [PCA_Deployment_ARO/testresults.md](PCA_Deployment_ARO/testresults.md)

### Single-User Latency

| Metric | Short (128/128) | Medium (512/256) | Long (2048/512) |
|--------|-----------------|-------------------|-----------------|
| TTFT | 57 ms | 117 ms | 1,020 ms |
| ITL | 6.8 ms | 6.8 ms | 6.9 ms |
| E2E latency | 0.93 s | 1.86 s | 4.52 s |
| Output tokens/s | 138 | 138 | 139 |

Inter-token latency is remarkably consistent at ~6.8 ms across all prompt sizes,
translating to ~138 output tokens/second for a single user.

### Peak Throughput

| Metric | Short (128/128) | Medium (512/256) | Long (2048/512) |
|--------|-----------------|-------------------|-----------------|
| Output tokens/s | 2,781 | 2,008 | 1,263 |
| Requests/s | 20.7 | 7.6 | 2.4 |

### Capacity Planning Summary

| Total Developers | Concurrent (30%) | Output tok/s | Tok/s Per User | ITL (ms) | Experience |
|:----------------:|:-----------------:|:------------:|:--------------:|:--------:|:----------:|
| 10 | 3 | ~270 | ~90 | ~10 | Excellent |
| 20 | 6 | ~420 | ~70 | ~13 | Excellent |
| 50 | 15 | ~700 | ~47 | ~21 | Good |
| 100 | 30 | ~1,000 | ~33 | ~30 | Acceptable |

For multi-GPU scaling recommendations and detailed capacity planning tables, see
[PCA_Deployment_ARO/testresults.md](PCA_Deployment_ARO/testresults.md).

---

## Key Differences from ROSA Deployment

| Aspect | ROSA (AWS) | ARO (Azure) |
|--------|-----------|-------------|
| GPU VM | `g6e.2xlarge` (L40S 48 GB) | `Standard_NC24ads_A100_v4` (A100 80 GB) |
| GPU provisioning | RHCS machine pool via Terraform | MachineSet script post-cluster (Gen2 image required) |
| Storage class | `gp3-csi` | `managed-csi` |
| IDP | HTPasswd via RHCS Terraform resource | kubeadmin + manual HTPasswd |
| Cluster creation | Terraform RHCS provider | `az aro create` via `null_resource` (handles SP internally) |
| NSG | AWS Security Groups (managed) | None on subnets (ARO-managed) |
| RHOAI channel | `stable-2.19` | `stable-3.x` (RHOAI 3.3.2) |
| AI Gateway | Technology Preview | **GA** |
| vLLM max-model-len | 32,768 (L40S 48 GB) | **65,536** (A100 80 GB) |
| vLLM version | RHOAI default | **0.17.1** (upstream, qwen3_5_moe support) |
| NFD | Pre-installed | **Manual install required** |

---

## Roadmap

- [ ] Upgrade to RHOAI 3.4+ when GA — eliminates the vLLM 0.17.1 manual workaround
- [ ] Add architecture diagrams: Azure infrastructure view, AI serving traffic flow
- [ ] Evaluate Azure Reserved Instance pricing for 1-year commitment
- [ ] Test with Gemma 4 Coder when vLLM support is available in RHOAI GA
- [x] Run `guidellm` sweep and populate benchmark table
- [x] Test Roo Code, Continue, and Cline end-to-end within ARO Dev Spaces
- [x] Validate HTPasswd IDP configuration for DevSpaces user onboarding
