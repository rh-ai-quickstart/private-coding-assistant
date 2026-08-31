# Semantic Router

Chat still hits Service `pca-semantic-router` when the hop is on. That Service is now official vLLM Semantic Router plus Envoy, not the old Python keyword proxy.

## Why the Python hop went away

The stand-in used substring matches (`code in decode`), one external URL, and `pin-local` / `auto`. That could not express extra-model strength or an embedding complexity split, and it was never the upstream router.

## Approach

- Same DNS: Guardrails and the MaaS chat HTTPRoute still target `pca-semantic-router:80`.
- Envoy plus ExtProc stay **inside** that Service. They are not attached to `maas-default-gateway` / RHCL.
- Signals: keyword `code` and a CPU complexity embedding (`sentence-transformers/all-MiniLM-L6-v2` by default). No MMLU domain tree, jailbreak, PII, fusion, or loopers. Guardrails already owns safety.
- `/tokenize` and `/detokenize` skip ExtProc and go to llm-d HTTP `:80` at the vLLM root (TrustyAI). Only `/v1/chat/completions` is classified.
- Tab `/local/v1` still skips Guardrails and SR.

## Local Qwen

Helm always injects the cluster model from `model.id` (and `model.servedName` when set) as provider `local`, strength weak, llm-d `:80`. Operators never list it in `models[]` or Terraform JSON.

## Options

| Setting | Chat behavior |
|---------|----------------|
| SR off (parent default; ARO overlay) | After Guardrails (if on), llm-d. No SR pod. |
| SR on, no extras | Pin to local Qwen. ROSA overlay already enables this hop. |
| SR on, extras | Code keyword **or** complexity `hard` → strongest extra. Complexity `easy` and not code → local Qwen. Fallback → local Qwen. |
| Extra backend | Any OpenAI-compatible URL: `endpoint`, `modelId`, `strength`, AI-ns Secret (`apiKeysJson` or `apiKeySecret`). |

Set **both** Helm flags together: `semanticRouter.enabled` and `global.semanticRouter.enabled`. Render fails if they differ. `pca-llm-upstream` is gone.

`semanticRouter.enabled=false` skips the Service; split-routing tests do not run.

## Inject

Secrets stay out of Git.

**ROSA / ARO** — `huggingface_token` on pca-platform-config. SR extras on pca-ai-serving. Terraform:

1. `huggingface_token` — local Qwen and MiniLM. Enabling routing without it fails apply.
2. `semantic_router_enabled = true` — JSON extras do not turn routing on. Leave the variable unset so the chart overlay wins (ROSA on, ARO off). Do not default Terraform to `false`; that would override ROSA.
3. `semantic_router_models_json` + `semantic_router_api_keys_json` — extras only. `[]` / `{}` pins to Qwen.
4. `model_variant` — which local Qwen Helm injects (`qwen3.6` vs `qwen3.8`).

See `terraform.tfvars.example` on both clouds.

**Existing OpenShift** — `.env`:

```
HUGGINGFACE_TOKEN=hf_...
SEMANTIC_ROUTER_ENABLED=true
SEMANTIC_ROUTER_MODELS_JSON=[]
SEMANTIC_ROUTER_API_KEYS_JSON={}
```

Make already requires `HF_TOKEN`. When `SEMANTIC_ROUTER_ENABLED=true` it sets both Helm flags and `--set-json` for extras. `HELM_ARGS` remains an escape hatch.

Override the embedding model with `semanticRouter.embedding.model`.

## Not taken

- ExtProc on the product front door
- Domain / MMLU, fusion, loopers
- Provider keys in DevSpaces
- Tab traffic through SR
- Teaching IDEs extra model names

## Related

- [Models and routing](models-and-routing.md)
- [Architecture](architecture.md)
