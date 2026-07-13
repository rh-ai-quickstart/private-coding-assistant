# PCA AI serving — TODOs

## Observability / attribution

- [x] **Cline attribution:** Per-namespace Cline ConfigMaps (`cline-provider-config`, `cline-home-provider-config`) send `X-PCA-User` / `X-PCA-DevSpace` / optional `X-PCA-Team` (same pattern as Roo + Continue). Cline may still require selecting the OpenAI-compatible provider once in the UI if it ignores the seeded JSON.

- [x] **Prompt/completion I/O capture:** `langfuse.ioCapture: metadata|full` (default **`full`**). When Langfuse is enabled and `ioCapture=full`, a vLLM `--middleware` stores full prompt/completion bodies in Langfuse after each response (async; does not block TTFT). OTEL path remains metadata (tokens/latency). Opt out of bodies: `--set langfuse.ioCapture=metadata --set pca-observability.langfuse.ioCapture=metadata`.

- [ ] **Phase 0 attribution spike:** Prove on-cluster that `X-PCA-*` headers appear on vLLM/LLMISVC OTEL spans and map to Langfuse `userId`/tags via the Collector transform. Full I/O path already reads `X-PCA-*` in the vLLM middleware. If OTEL attribution fails: keep aggregate Grafana B/C; rely on middleware userId for boards A/D until fixed.
