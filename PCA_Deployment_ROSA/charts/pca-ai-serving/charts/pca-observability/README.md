# pca-observability

Minimal LLM observability for PCA AI serving: **Grafana** (ops metrics) + optional **Langfuse** (LLM traces) + **OTel Collector**.

Nested under `pca-ai-serving` — deploys with the same Helm release as llm-d/vLLM.

## Flags

| Flag | Default | Effect |
|------|---------|--------|
| `observability.enabled` (parent) | `true` | Installs this subchart |
| `grafana.enabled` | `true` | Grafana 1-pod + boards B/C (A/D when Langfuse on) |
| `langfuse.enabled` | `false` | Langfuse + OTel Collector + OTLP on LLMInferenceService |
| `langfuse.ioCapture` | `full` | `full` = vLLM middleware stores prompt/completion in Langfuse; `metadata` = OTEL tokens/latency only |

Keep parent top-level `grafana.enabled` / `langfuse.enabled` / `langfuse.ioCapture` in sync with `pca-observability.*`.

### Enable Langfuse (opt-in)

```bash
make ai-serving-deploy-existing-openshift HF_TOKEN=hf_xxx \
  HELM_ARGS='--set langfuse.enabled=true --set pca-observability.langfuse.enabled=true'
```

With Langfuse on, **full prompt/completion storage is the default** (`ioCapture: full`) via an in-process vLLM middleware (async after response — no IDE hop). Opt out of bodies:

```bash
HELM_ARGS='--set langfuse.enabled=true --set pca-observability.langfuse.enabled=true \
  --set langfuse.ioCapture=metadata --set pca-observability.langfuse.ioCapture=metadata'
```

## Prometheus access modes

| Mode | When | Thanos URL | RBAC |
|------|------|------------|------|
| `cluster` (default) | ROSA full provision | `:9091` | `cluster-monitoring-view` |
| `namespace` | Existing OpenShift | `:9092` | namespace `view` |

`deploy_existing_openshift/values-ai-serving.yaml` sets `accessMode: namespace`.

## Routes

```bash
oc get route pca-grafana -n <AI_NS>
oc get route pca-langfuse -n <AI_NS>   # only if langfuse.enabled
```

## Retrieve generated credentials

```bash
# Grafana admin
oc get secret pca-grafana-admin -n <AI_NS> -o jsonpath='{.data.admin-password}' | base64 -d; echo

# Langfuse init user + API keys (OTLP auth uses the same project keys)
oc get secret pca-langfuse-credentials -n <AI_NS> -o jsonpath='{.data.init-user-password}' | base64 -d; echo
oc get secret pca-langfuse-credentials -n <AI_NS> -o jsonpath='{.data.init-project-public-key}' | base64 -d; echo
oc get secret pca-langfuse-credentials -n <AI_NS> -o jsonpath='{.data.init-project-secret-key}' | base64 -d; echo
```

Optional values overrides (`grafana.adminPassword`, `langfuse.salt`, …) skip random generation when set.

## Dashboards (A–D)

| Board | Content | Requires Langfuse |
|-------|---------|-------------------|
| A | Users overview (aggregate + Langfuse pointer) | yes |
| B | UX / latency (TTFT, ITL, e2e) | no |
| C | Capacity / KV / GPU (+ PLACEHOLDER $/hr) | no |
| D | Tokens / cost fairness | yes |

## GPU cost PLACEHOLDER

`cost.gpuHourlyUsd: 1.86` is an **illustrative** L40S on-demand figure from the sizing doc — **not** billing truth.

- `cost.gpuHourlyUsdIsPlaceholder: true` (default)
- Panel titles include **PLACEHOLDER — override per cluster**
- Set a real rate and `gpuHourlyUsdIsPlaceholder: false` per cluster

## Attribution (X-PCA-*)

DevSpaces (Roo + Continue + Cline) send:

- `X-PCA-User` ← Helm `devspaces[].user` → Langfuse `userId`
- `X-PCA-DevSpace` ← namespace → metadata `devspace`
- `X-PCA-Team` ← optional `devspaces[].team` → metadata/tag `team`

Guardrails proxy forwards these headers. Full prompt/completion bodies are stored by the **vLLM middleware** when `langfuse.ioCapture=full` (reads the same headers for `userId`/metadata).

**Phase 0 risk:** vLLM OTEL span attribute mapping for `X-PCA-*` is still unproven for Boards A/D aggregates from OTEL alone. The full-I/O middleware path does not depend on that.

## Persistence

Modest defaults when Langfuse is on: Postgres ~10Gi, ClickHouse ~20Gi, MinIO ~10Gi. Omit `storageClassName` (cluster default) unless `persistence.storageClass` / bitnami persistence overrides are set. Grafana is ephemeral (ConfigMap dashboards).
