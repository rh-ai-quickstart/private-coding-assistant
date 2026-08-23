# pca-observability

Minimal LLM observability for PCA AI serving: **Grafana** (ops metrics) + optional **Langfuse** (LLM traces) + **OTel Collector**.

Nested under `pca-ai-serving` — deploys with the same Helm release as llm-d/vLLM.

## Flags

| Flag | Default | Effect |
|------|---------|--------|
| `observability.enabled` (parent) | `true` | Installs this subchart |
| `grafana.enabled` | `true` | Grafana 1-pod + boards B/C/E/F/G (A/D when Langfuse on) |
| `langfuse.enabled` | `false` | Langfuse + OTel Collector + OTLP on LLMInferenceService (set as `pca-observability.langfuse.*` from parent) |
| `langfuse.ioCapture` | `full` | `full` = vLLM middleware stores prompt/completion in Langfuse; `metadata` = OTEL tokens/latency only |
| `otelCollector.debugExporter` | `true` | OTel Collector also logs every span to stdout; set `false` to silence under load |

Parent LLMInferenceService wiring reads `pca-observability.langfuse.*` — one flag enables both the stack and vLLM OTLP/middleware.

### Enable Langfuse (opt-in)

```bash
make ai-serving-deploy-existing-openshift HF_TOKEN=hf_xxx \
  HELM_ARGS='--set pca-observability.langfuse.enabled=true'
```

With Langfuse on, **full prompt/completion storage is the default** (`ioCapture: full`) via an in-process vLLM middleware (async after response — no IDE hop). Opt out of bodies:

```bash
HELM_ARGS='--set pca-observability.langfuse.enabled=true \
  --set pca-observability.langfuse.ioCapture=metadata'
```

## Prometheus access modes

| Mode | When | Thanos URL | RBAC |
|------|------|------------|------|
| `cluster` (default) | ROSA full provision | `:9091` | `cluster-monitoring-view` |
| `namespace` | Existing OpenShift | `:9092` | namespace `view` (+ GPU operator NS for Board C) |

`deploy_existing_openshift/values-ai-serving.yaml` sets `accessMode: namespace`.

In **namespace** mode, Board C GPU panels use a second datasource (`prometheus-gpu`) that queries `prometheus.gpuMetricsNamespace` (default `nvidia-gpu-operator`). Override if your DCGM exporter lives elsewhere (e.g. `openshift-nvidia-gpu-operator`).

### Cluster prerequisites (ROSA/ARO full provision only)

These are provisioned automatically by `pca-platform-config` when `clusterConfig.enabled: true` (the ROSA/ARO default):

- **User Workload Monitoring** — without it, Prometheus never scrapes the PodMonitor/ServiceMonitor objects that KServe creates for vLLM or that this chart creates for the AI Gateway, and every model/gateway board renders with no data.
- **`nvidia-dcgm-exporter` ServiceMonitor** — the GPU Operator starts the DCGM exporter but does not register a ServiceMonitor for it; without one, all GPU panels on Board C (utilization, framebuffer, temperature, power) render with no data.

On existing OpenShift (`clusterConfig.enabled: false`), enable both manually — see `deploy_existing_openshift/README.md`.

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

Optional values overrides (`grafana.adminPassword`, `langfuse.credentials.salt`, …) skip random generation when set.

**Salt note:** `salt` is plain text in `stringData` (Kubernetes base64-encodes once). If an older install double-encoded it, delete `pca-langfuse-credentials` and redeploy, or set `langfuse.credentials.salt` explicitly.

## Dashboards (A–G)

| Board | Content | Requires Langfuse |
|-------|---------|-------------------|
| A | Users overview (finished inference req/s, running vs queued, input vs output tokens/sec + Langfuse pointer) | yes |
| B | UX / latency (TTFT, inter-token latency, end-to-end request latency, queue wait) | no |
| C | Capacity / KV / GPU (KV cache %, GPU util avg+peak, GPU temp/power, output vs all tokens/sec, finished req/min, preemptions/min, model up + restarts, guardrails blocked requests, PLACEHOLDER $/hr) | no |
| D | Tokens / cost fairness (input vs output tokens/sec, finished req/s, PLACEHOLDER GPU $/hr) | yes |
| E | AI Gateway (request rate by response class, error rate, gateway latency, auth denials, Kuadrant allow/deny, gateway pod health) | no |
| F | DevSpaces (active workspace pods per developer, start success rate, startup time, per-developer CPU/memory) | no |
| G | Platform Health (ArgoCD app health/sync, GPU node capacity, pod restarts, PVC usage) | no |

Panel titles use long, definition-style names (same style as the performance ladder columns). Token naming: **output** = generation/decode only; **input/all** keep prompt visible. Grafana uses rolling 5m `rate()`; the ladder uses total stage time — same token kind, different time base.

Boards E–G need the cluster prerequisites above (UWM + DCGM ServiceMonitor). Board E also needs the `pca-ai-gateway` PodMonitor this chart creates against the Istio-managed AI Gateway/llm-d gateway pods (`gateway.istio.io/managed=istio.io-gateway-controller`).

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

Guardrails proxy forwards these headers. Flagged requests (input skip or output detection) are stored by the proxy as Langfuse traces named `guardrails-flagged` (tags `guardrails:blocked` / `guardrails:warned`). Full prompt/completion bodies for allowed chats are stored by the **vLLM middleware** when `langfuse.ioCapture=full` (reads the same headers for `userId`/metadata).

**Phase 0 risk:** vLLM OTEL span attribute mapping for `X-PCA-*` is still unproven for Boards A/D aggregates from OTEL alone. The full-I/O middleware path does not depend on that.

## Persistence

Modest defaults when Langfuse is on: Postgres ~10Gi, ClickHouse ~20Gi, MinIO ~10Gi. Omit `storageClassName` (cluster default) unless `persistence.storageClass` / bitnami persistence overrides are set. Grafana is ephemeral (ConfigMap dashboards).
