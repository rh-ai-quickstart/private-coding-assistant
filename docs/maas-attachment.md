# MaaS attachment (spike)

PCA owns HTTPRoutes on `maas-default-gateway`. `MaaSModelRef` publishes the local `LLMInferenceService` so MaaS can mint keys and enforce token quota. It does not choose chat vs tab vs external.

## Why not `endpointOverride`

`MaaSModelRef.spec.endpointOverride` changes the URL MaaS advertises in the dashboard and API catalog. It does not replace Envoy routing. The MaaS controller still creates its own HTTPRoutes toward `LLMInferenceService` or `ExternalModel`.

`kind` on `MaaSModelRef` is only `LLMInferenceService` or `ExternalModel`. Semantic Router is neither. Do not point MaaS at SR through that CR.

## What PCA attaches

HTTPRoute `pca-maas-front-door` in the AI namespace, `parentRefs` to `Gateway/maas-default-gateway` in `openshift-ingress`.

| Path | Backend |
|------|---------|
| `/v1/chat/completions` | `guardrails-proxy` when guardrails is on, else Semantic Router when that is on, else llm-d HTTP `:80` |
| `/local/v1` | llm-d HTTP `:80` (URLRewrite prefix to `/v1`). Continue tab uses this. |
| `/v1` | llm-d HTTP `:80` (`/v1/models`, `/v1/completions`) |

AuthPolicy on that HTTPRoute accepts per-DevSpace API keys (same Authorino pattern as the retired `pca-ai-gateway`). MaaS subscription CRs still feed Limitador token quota on the shared gateway.

If a cluster already has MaaS-generated `/llm/<model>/v1` routes, leave them. IDEs call ClusterIP `/v1` and `/local/v1`.

Helm still mints Authorino API keys (`pca-maas-apikey`) so IDEs work without a live `maas-api` mint Job. A Gateway-level MaaS AuthPolicy might AND with PCA's HTTPRoute AuthPolicy; if that happens, prefer the HTTPRoute policy for IDE `/v1`.

## Gateway lock

Do not use `allowedRoutes.namespaces.from: All` ([RHOAIENG-80360](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.4/html/release_notes/known-issues_relnotes)). Use a namespace selector `pca.ai/allow-maas-routes: "true"` on the AI namespace (and `models-as-a-service` if the operator’s routes live there).

## Existing OpenShift

Helm `pca-platform-config` often has `clusterConfig.enabled: false` (no DSC/NFD), but it still owns Gateway+TLS when `maas.gateway.create` is true (chart default). Patch DSC `kserve.modelsAsService` to `Managed`. Pass `maas.hostname=<Gateway/Route host>` via `HELM_ARGS` when known so HTTPRoute, AuthConfig, and EnvoyFilter share that vhost; leave it empty for Istio catch-all `*:443`. Do not write the live cluster hostname into committed values files.
