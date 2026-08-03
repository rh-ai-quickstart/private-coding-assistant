# Changing models and hardware

How to swap the served model or the GPU accelerator without forking the platform charts.

## Changing the model

Two values must always match — the serving chart and the DevSpaces chart each need the same HuggingFace model identifier.

| Chart | Key | Role |
|-------|-----|------|
| `pca-ai-serving` | `model.id` | vLLM `--model` argument and OpenAI API model name |
| `pca-devspaces` | `modelId` | Pre-wired model name in IDE ConfigMaps |

### Which files to edit

| Deployment path | `pca-ai-serving` file | `pca-devspaces` file |
|-----------------|----------------------|---------------------|
| ROSA GitOps | `charts/pca-ai-serving/values-rosa.yaml` | `charts/pca-devspaces/values-rosa.yaml` |
| ARO GitOps | `charts/pca-ai-serving/values-aro.yaml` | `charts/pca-devspaces/values-aro.yaml` |
| Existing OpenShift | `deploy_existing_openshift/values-ai-serving.yaml` | `deploy_existing_openshift/values-devspaces*.yaml` |

The base `charts/pca-ai-serving/values.yaml` sets the default; cloud overlays and the existing-OpenShift files override it.

### Fields to review when changing the model

**Always set:**

| Field | Description |
|-------|-------------|
| `model.id` | Full HuggingFace path (e.g. `meta-llama/Llama-3.1-70B-Instruct`) |
| `model.name` | Short k8s-safe name used for resource names (e.g. `llama-31-70b`) |
| `model.poolName` | InferencePool name; must be unique per cluster namespace |
| `model.servedName` | Leave empty — so the OpenAI API model name equals `model.id` |

**For newer models not yet supported by RHOAI's bundled vLLM:**

| Field | Description |
|-------|-------------|
| `vllm.useCustomRuntime: true` | Deploys a ServingRuntime + InferenceService instead of LLMInferenceService |
| `vllm.image` | Upstream vLLM image tag that supports the model architecture (e.g. `vllm/vllm-openai:v0.19.0` for Qwen3.6) |

**Model-specific parsers (set to empty string if the model does not use them):**

| Field | Example values |
|-------|---------------|
| `vllm.toolCallParser` | `qwen3_xml`, `llama3_json`, `hermes` |
| `vllm.reasoningParser` | `qwen3` (only for thinking-mode models) |

### VRAM rule of thumb

| Model weight class | Min VRAM |
|-------------------|----------|
| 7–8 B FP8 | 24 GB (single GPU) |
| 14–15 B FP8 | 48 GB |
| 32–35 B FP8 (MoE, e.g. Qwen3.6) | 48 GB |
| 70–72 B FP8 | 80 GB |

Detailed sizing: [GPU Sizing Considerations](../assets/GPU_Sizing_Considerations_for_AI_Code_Assistant_v3.md) and [benchmarks](benchmarks.md).

---

## Changing the hardware

### GPU SKU comparison

| GPU | VRAM | Typical instance | Notes |
|-----|------|-----------------|-------|
| NVIDIA L40S | 48 GB | `g6e.2xlarge` (ROSA/AWS) | MoE FP8 models up to ~35 B; good price/VRAM ratio |
| NVIDIA A100 80 GB | 80 GB | `g5.48xlarge` (ROSA/AWS) | 70 B FP8; standard data-center card |
| NVIDIA H100 NVL 94 GB | 94 GB | `Standard_NC40ads_H100_v5` (ARO/Azure) | Default for ARO; highest throughput for code generation |

### ROSA (AWS) — changing the GPU instance type

Edit `PCA_Deployment_ROSA/terraform/terraform.tfvars`:

```hcl
gpu_instance_type = "g6e.2xlarge"   # change to target instance family
```

Also update the node selector in `charts/pca-ai-serving/values-rosa.yaml` so vLLM pods land on the right pool:

```yaml
hardware:
  gpuProduct: "g6e.2xlarge"          # must match gpu_instance_type
  instanceTypeLabel: "node.kubernetes.io/instance-type"
```

### ARO (Azure) — changing the GPU VM size

Edit `PCA_Deployment_ARO/terraform/terraform.tfvars`:

```hcl
gpu_vm_size = "Standard_NC40ads_H100_v5"   # change to target VM family
```

Also update the node selector in `charts/pca-ai-serving/values-aro.yaml`:

```yaml
hardware:
  gpuProduct: "Standard_NC40ads_H100_v5"
  instanceTypeLabel: "node.kubernetes.io/instance-type"
```

### Existing OpenShift — changing hardware

GPU nodes are provisioned outside this repo. Ensure nodes are labeled and the GPU Operator has detected them. Verify the model fits the available VRAM before deploying, then update `hardware.gpuProduct` in `deploy_existing_openshift/values-ai-serving.yaml` to match your node label.

### AWS Inferentia2 (ROSA only, optional)

Enable an Inferentia pool for additional capacity:

```hcl
# PCA_Deployment_ROSA/terraform/terraform.tfvars
inferentia_pool_enabled  = true
inferentia_instance_type = "inf2.24xlarge"
inferentia_pool_replicas = 1
```

Caveats:
- MoE prefix-caching is limited on Neuron; prefer NVIDIA for Qwen3-Coder workloads
- OVN annotation timing can break Neuron pod networking on first boot — see [ROSA README troubleshooting](../PCA_Deployment_ROSA/README.md#inferentia--neuron-pods-fail-networking-ovn-annotation-race)

---

## Related

- [Models and routing](models-and-routing.md) — architecture, llm-d scoring, RHCL front door
- [Requirements](requirements.md) — minimum hardware per deployment path
- [Benchmarks](benchmarks.md) — throughput and latency by GPU and model
- [GPU Sizing Considerations](../assets/GPU_Sizing_Considerations_for_AI_Code_Assistant_v3.md)
