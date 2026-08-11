# Benchmarks

Short highlights only. Full GuideLLM sweeps live next to the cloud deploy trees and in the GPU sizing assets.

## Run GuideLLM on the live cluster (`make performance-vllm`)

Measures **TTFT**, **ITL/TPOT**, **token throughput**, and **error/timeout behavior** against the currently deployed vLLM **predictor** (HTTP `qwen3-coder-predictor`; GuideLLM Job in `charts/pca-benchmarks`). Defaults avoid HTTPS llm-d because the pinned GuideLLM image cannot skip self-signed TLS verify.

```bash
# AI serving already deployed. Do not run alongside make performance (OpenCode) — shared GPU.
make performance-vllm AI_NAMESPACE=<your-ai-ns>

oc logs -n <your-ai-ns> -f job/guidellm-capacity
```

| Knob | Default | Where |
|------|---------|--------|
| Concurrent streams | `1,4,8,16` | `charts/pca-benchmarks/values.yaml` → `streams` |
| Max requests / level | `50` | `maxRequests` → GuideLLM `--max-requests` |
| Workload shapes | short / large / near-max (see `workloads[]`) | `promptTokens` + `outputTokens` ≤ 32K |
| Throughput probe | off | `runThroughputProbe` |
| Override | `--set streams=1\,4\,16` or `-f` with `streams: "1,4,16"` | `HELM_ARGS=` on the Make target (escape commas in `--set`) |

### Results

The Job is **stateless** — read GuideLLM tables from Job logs (no PVC):

```bash
oc logs -n <your-ai-ns> -f job/guidellm-capacity
# After finish:
oc logs -n <your-ai-ns> job/guidellm-capacity > guidellm-capacity.log
```

Useful columns when summarizing (same spirit as [ARO H100 tables](../PCA_Deployment_ARO/testresults_h100.md)):

| Column | Meaning |
|--------|---------|
| Concurrency / streams | In-flight request streams |
| Output tok/s, total tok/s | Generation and aggregate throughput |
| TTFT (p50/p95) | Time to first token |
| ITL / TPOT | Inter-token / time-per-output-token |
| Latency | End-to-end request latency |
| Error / timeout rate | Must sit next to peak tok/s — high tok/s with failures is not capacity |

**How to read a cliff:** as streams grow, watch for a step jump in p95 TTFT or errors while aggregate tok/s flattens or drops. On L40S 48GB with FP8 KV and `--max-num-batched-tokens=16384`, high-N × long-context shapes (16K / 28K prompts) often cliff earlier than H100 lab numbers — that is a capacity finding, not a broken Job.

GitOps (ROSA/ARO): enable via chart `values-*.yaml` (`enabled: true`); ARO already opts in.

## ARO — Qwen3.6-35B-A3B-FP8

### NVIDIA A100 80 GB (Central US)

| Metric | Single user | Peak (short / medium) |
|--------|-------------|------------------------|
| Output tok/s | ~138 | ~2,781 / ~2,008 |
| TTFT | ~57–117 ms (short/medium) | — |
| ITL | ~6.8 ms | — |

Capacity planning (≈30% concurrent, medium 512/256): roughly **3–4 interactive developers per GPU** at a comfortable SLO; 50 developers ≈ 1 GPU “good”; 100 developers ≈ 2 GPUs “acceptable.”

Full tables: [PCA_Deployment_ARO/testresults.md](../PCA_Deployment_ARO/testresults.md)

### NVIDIA H100 NVL 94 GB (Australia East)

| Workload | Prompt / output | Peak total tok/s | Sync latency | Sync TTFT |
|----------|-----------------|------------------|--------------|-----------|
| Code completion | 256 / 128 | ~4,512 | 0.70 s | ~36 ms |
| Code generation | 1,024 / 512 | ~12,790 | 2.78 s | ~83 ms |
| Code review | 4,096 / 1,024 | ~16,133 | 5.59 s | ~157 ms |
| File generation | 8,192 / 2,048 | ~13,976 | 11.15 s | ~208 ms |

Full tables: [PCA_Deployment_ARO/testresults_h100.md](../PCA_Deployment_ARO/testresults_h100.md)

## ROSA — Qwen3-Coder-30B (NVIDIA L40S, historical)

Validated patterns on ROSA HCP with `Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8` on g6e (L40S):

- Single-user ITL ~10 ms; TTFT often ~265–335 ms through the gateway stack
- Two-replica llm-d load balancing with prefix-cache affinity observed under repeated system prompts
- Prefer NVIDIA FP8 for MoE code models vs Inferentia BF16 for latency and $/token

Use current chart values and [GPU sizing](../assets/GPU_Sizing_Considerations_for_AI_Code_Assistant_v3.md) for capacity planning rather than dated lab dumps.

## Sizing and TCO

- [GPU sizing considerations (v3)](../assets/GPU_Sizing_Considerations_for_AI_Code_Assistant_v3.md)
- GuideLLM Job: `charts/pca-benchmarks` — `make performance-vllm` on existing OpenShift; GitOps opt-in via cloud values

## Related

- [Models and routing](models-and-routing.md)
- [ARO deploy guide](../PCA_Deployment_ARO/README.md)
