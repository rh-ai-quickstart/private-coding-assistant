# Benchmarks

Short highlights only. Full GuideLLM sweeps live next to the cloud deploy trees and in the GPU sizing assets.

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
- Optional GuideLLM Job: `charts/pca-benchmarks` (disabled by default; opt-in via cloud values)

## Related

- [Models and routing](models-and-routing.md)
- [ARO deploy guide](../PCA_Deployment_ARO/README.md)
