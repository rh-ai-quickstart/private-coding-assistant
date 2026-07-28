# Models and routing

## Serving

NVIDIA models are deployed with KServe **`LLMInferenceService`** (or cloud-specific ServingRuntime + InferenceService where the chart uses that pattern). The stack provisions:

- vLLM pods (RawDeployment)
- InferencePool / InferenceModel (Gateway API Inference Extension)
- llm-d Endpoint Picker (EPP)
- HTTPRoute through the data-science / llm-d gateway
- Optional **RHCL AI Gateway** (`pca-ai-gateway`) with AuthPolicy in front of llm-d

Model ID, context length, and GPU sizing are set per cloud in `charts/pca-ai-serving/values-rosa.yaml` / `values-aro.yaml` (or `deploy_existing_openshift/values-ai-serving.yaml`).

## llm-d scoring

The EPP typically weights:

| Scorer | Effect |
|--------|--------|
| Prefix-cache | Prefer pods that already hold the prompt prefix |
| KV-cache utilization | Prefer pods with KV headroom |
| Queue depth | Prefer shorter queues |

Shared system prompts and similar file context benefit from prefix-cache-aware routing (lower TTFT under multi-user load).

## Accelerator notes

| Preference | Why |
|------------|-----|
| **NVIDIA GPU (primary)** | FP8, prefix caching for MoE code models, longer context, simpler ops |
| AWS Inferentia2 (optional / lab) | Possible overflow capacity on ROSA; MoE prefix caching limited on Neuron; extra scheduler complexity |

For MoE code models (e.g. Qwen3-Coder / Qwen3.6 MoE), prefer NVIDIA with FP8. Dense models may be more cost-competitive on Inferentia when prefix caching is available.

## RHCL front door

IDE traffic should use **`pca-ai-gateway`**, not raw vLLM. Auth is API-key based per Dev Spaces namespace. The llm-d gateway is left unmanaged by OpenShift AI AuthPolicies that would conflict with RHCL (`opendatahub.io/managed=false` where applicable).

Details: [deploy_existing_openshift/README.md](../deploy_existing_openshift/README.md) (RHCL prerequisite) and chart docs under `charts/pca-ai-serving/`.

## Related

- [Architecture](architecture.md)
- [Benchmarks](benchmarks.md)
- [IDE and extensions](ide-and-extensions.md)
