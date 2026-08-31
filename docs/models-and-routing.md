# Models and routing

## Serving

NVIDIA models are deployed with KServe **`LLMInferenceService`** only. The stack provisions:

- vLLM pods (RawDeployment)
- InferencePool / InferenceModel (Gateway API Inference Extension)
- llm-d Endpoint Picker (EPP)
- HTTPRoute through the data-science / llm-d gateway
- **MaaS / RHCL front door** (`maas-default-gateway`) with AuthPolicy on `pca-maas-front-door`
- Optional **Semantic Router** (`semanticRouter.enabled`, default off) as an HTTP hop after TrustyAI. See [semantic-router.md](semantic-router.md).

### Default model

The default HuggingFace model is **`Qwen/Qwen3.6-35B-A3B-FP8`**. Leave `model.servedName` empty so the OpenAI API model name equals `model.id` (never point `servedName` at a different model).

Qwen3.6 needs a new enough vLLM (`vllm.image`, already set in the chart defaults on the LLMInferenceService).

Workload TLS is a **hard prerequisite**: cluster `enableLLMInferenceServiceTLS=true` (KServe mounts `/var/run/kserve/tls`; the chart hardcodes `--ssl-*` and HTTPS probes). See [deploy_existing_openshift/README.md](../deploy_existing_openshift/README.md#prerequisite-llminferenceservice-workload-tls).

### Choosing a different model

Set the same identifier in both places:

| Chart | Field | Files |
|-------|-------|--------|
| `pca-ai-serving` | `model.id` | `charts/pca-ai-serving/values.yaml`, `values-rosa.yaml` / `values-aro.yaml`, or `deploy_existing_openshift/values-ai-serving.yaml` |
| `pca-devspaces` | `modelId` | `charts/pca-devspaces/values.yaml` / cloud overlays, or `deploy_existing_openshift/values-devspaces*.yaml` |

Context length and GPU sizing stay per cloud in those same values files. Pick any compatible model your organization accepts (including non-Chinese-origin weights when required by policy).

Step-by-step guide: [models-and-hardware.md](models-and-hardware.md)

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

Hardware how-to: [models-and-hardware.md — Changing the hardware](models-and-hardware.md#changing-the-hardware)

Optional ROSA Inferentia pool: enable with Terraform `inferentia_pool_enabled=true`. If Neuron pods fail networking on OVN-Kubernetes, see [Inferentia / Neuron pods fail networking (OVN annotation race)](../PCA_Deployment_ROSA/README.md#inferentia--neuron-pods-fail-networking-ovn-annotation-race).

## MaaS / RHCL front door

IDE traffic uses **`maas-default-gateway`** in `openshift-ingress`, not raw vLLM and not `pca-ai-gateway`. Auth is API-key based per Dev Spaces namespace (`pca-maas-apikey`). The llm-d gateway stays unmanaged by OpenShift AI AuthPolicies (`opendatahub.io/managed=false`).

HTTPRoute `pca-maas-front-door`:

| Path | Backend |
|------|---------|
| `/v1/chat/completions` | `guardrails-proxy` when guardrails is on, else Semantic Router when that is on, else llm-d HTTP `:80` |
| `/local/v1` | llm-d HTTP `:80` (prefix rewritten to `/v1`). Continue tab uses this with a real API key. |
| `/v1` | llm-d HTTP `:80` (`/v1/models`, `/v1/completions`) |

`MaaSModelRef` publishes the local `LLMInferenceService` for catalog and token quota. It does not pick chat vs tab vs external — see [maas-attachment.md](maas-attachment.md).

OpenCode has a single `OPENAI_BASE_URL` (`/v1`), so autocomplete that uses chat completions still follows the guarded path.

Details: [deploy_existing_openshift/README.md](../deploy_existing_openshift/README.md) (RHCL + MaaS DSC patch) and [charts/pca-ai-serving](../charts/pca-ai-serving/).

## Semantic Router

Optional official vLLM Semantic Router plus Envoy, still Service `pca-semantic-router`. Community workload, not an OpenShift AI DSC component. ExtProc is wrapped in that Service; it is not attached to `maas-default-gateway`.

Full operator notes: [semantic-router.md](semantic-router.md).

- **Off (parent default; ARO overlay):** TrustyAI pins llm-d HTTP `:80`. Chat stays local. Grafana SR panels are empty — that is expected.
- **On, no extras:** Helm injects local Qwen from `model.id`. Chat pins to that provider. ROSA overlay already enables this hop.
- **On, extras:** operators list extra OpenAI-compatible backends only (`endpoint`, `modelId`, `strength`). Code keywords or complexity `hard` go to the strongest extra; easy non-code stays on local Qwen. Keys stay in the AI namespace (`apiKeysJson` or `apiKeySecret`), never in DevSpaces.
- **Flags:** set `semanticRouter.enabled` and `global.semanticRouter.enabled` together. `/tokenize` stays on llm-d. Tab `/local/v1` skips SR.

Rotate extra-model keys by replacing the AI-ns Secret. Rotate IDE keys by replacing `pca-maas-apikey` (DevSpaces ns + Authorino mirror). Disable SR with both flags `false` — chat pins local via llm-d.

## Related

- [Architecture](architecture.md)
- [Semantic Router](semantic-router.md)
- [Benchmarks](benchmarks.md)
- [IDE and extensions](ide-and-extensions.md)
