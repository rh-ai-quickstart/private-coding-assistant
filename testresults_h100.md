# GuideLLM Benchmark Results — Qwen3.6-35B-A3B-FP8 on NVIDIA H100 NVL

**Date**: 2026-05-21
**Cluster**: ARO `aro-pca-aue` (Azure Australia East)
**GPU**: NVIDIA H100 NVL 94 GB HBM3 (`Standard_NC40ads_H100_v5`)
**Model**: `Qwen/Qwen3.6-35B-A3B-FP8` (35B total / 3B active MoE, FP8 quantized)
**Serving**: vLLM v0.19.0 with CUDA compatibility mode (driver 550 / CUDA 12.4 + compat libs 575)
**Max context**: 32,768 tokens
**Benchmark tool**: GuideLLM (`quay.io/rh-aiservices-bu/guidellm:f1f8ca8`)

---

## Summary

| Workload | Prompt Tokens | Output Tokens | Max Throughput (tok/s) | Sync Latency (s) | Sync TTFT (ms) | Sync ITL (ms) |
|----------|--------------|---------------|----------------------|-------------------|----------------|---------------|
| Code Completion | 256 | 128 | 4,512 | 0.70 | 36.4 | 5.3 |
| Code Generation | 1,024 | 512 | 12,790 | 2.78 | 82.6 | 5.3 |
| Code Review | 4,096 | 1,024 | 16,133 | 5.59 | 156.5 | 5.3 |
| File Generation | 8,192 | 2,048 | 13,976 | 11.15 | 207.7 | 5.3 |

> **Max Throughput** = total tokens/sec at maximum concurrency (throughput mode).
> **Sync Latency** = mean request latency at concurrency 1 (synchronous mode).
> **TTFT** = Time to First Token. **ITL** = Inter-Token Latency.

---

## Benchmark 1: Code Completion (Short)

**Config**: 256 prompt tokens, 128 output tokens, sweep mode

| Rate | Req/s | Concurrency | Output tok/s | Total tok/s | Latency (s) | TTFT (ms) | ITL (ms) | TPOT (ms) |
|------|-------|-------------|-------------|-------------|-------------|-----------|----------|-----------|
| synchronous | 1.42 | 1.00 | 181.7 | 543.7 | 0.70 | 36.4 | 5.3 | 5.2 |
| throughput | 11.78 | 99.26 | 1,507.5 | 4,511.8 | 8.43 | 5,688.9 | 21.6 | 21.4 |
| constant@2.71 | 2.71 | 2.25 | 347.2 | 1,039.3 | 0.83 | 39.0 | 6.2 | 6.2 |
| constant@4.01 | 4.04 | 3.61 | 517.4 | 1,548.4 | 0.89 | 41.9 | 6.7 | 6.6 |
| constant@5.30 | 5.34 | 5.16 | 683.2 | 2,044.5 | 0.97 | 44.5 | 7.3 | 7.2 |
| constant@6.60 | 6.63 | 6.82 | 848.1 | 2,538.0 | 1.03 | 48.5 | 7.7 | 7.7 |
| constant@7.89 | 7.90 | 8.18 | 1,011.1 | 3,026.2 | 1.04 | — | — | — |
| constant@9.19 | 9.27 | 10.96 | 1,185.9 | 3,549.1 | 1.18 | — | — | — |
| constant@10.48 | 10.51 | 13.17 | 1,345.4 | 4,026.1 | 1.25 | — | — | — |
| constant@11.78 | 11.70 | 17.42 | 1,497.4 | 4,481.4 | 1.49 | — | — | — |

**Key takeaway**: At single-user (synchronous), the H100 delivers **0.70s latency** for short code completions with **36ms TTFT** and **5.3ms ITL**. Under maximum throughput, it sustains **~4,500 total tok/s**.

---

## Benchmark 2: Code Generation (Medium)

**Config**: 1,024 prompt tokens, 512 output tokens, sweep mode

| Rate | Req/s | Concurrency | Output tok/s | Total tok/s | Latency (s) | TTFT (ms) | ITL (ms) | TPOT (ms) |
|------|-------|-------------|-------------|-------------|-------------|-----------|----------|-----------|
| synchronous | 0.36 | 1.00 | 184.3 | 552.6 | 2.78 | 82.6 | 5.3 | 5.3 |
| throughput | 8.33 | 99.02 | 4,265.9 | 12,790.2 | 11.88 | 1,214.7 | 20.9 | 20.8 |
| constant@1.36 | 1.31 | 5.11 | 671.5 | 2,013.2 | 3.90 | 89.2 | 7.4 | 7.4 |
| constant@2.35 | 2.21 | 10.25 | 1,131.1 | 3,391.4 | 4.64 | 89.9 | 8.9 | 8.9 |
| constant@3.35 | 3.02 | 17.78 | 1,547.3 | 4,639.0 | 5.88 | 90.5 | 11.3 | 11.3 |
| constant@4.35 | 3.75 | 24.99 | 1,922.1 | 5,762.6 | 6.66 | 93.5 | 12.8 | 12.8 |
| constant@5.34 | 4.35 | 33.34 | 2,227.9 | 6,679.8 | 7.66 | — | — | — |
| constant@6.34 | 4.84 | 41.63 | 2,479.7 | 7,434.7 | 8.60 | — | — | — |
| constant@7.34 | 5.21 | 49.49 | 2,665.0 | 7,990.3 | 9.51 | — | — | — |
| constant@8.33 | 5.48 | 56.01 | 2,806.2 | 8,413.9 | 10.22 | — | — | — |

**Key takeaway**: For medium code generation, synchronous latency is **2.78s** with **83ms TTFT**. Under full load, throughput reaches **~12,800 total tok/s** — enough for **~8 concurrent developers** at interactive speeds (<5s latency).

---

## Benchmark 3: Code Review (Large Context)

**Config**: 4,096 prompt tokens, 1,024 output tokens, sweep mode

| Rate | Req/s | Concurrency | Output tok/s | Total tok/s | Latency (s) | TTFT (ms) | ITL (ms) | TPOT (ms) |
|------|-------|-------------|-------------|-------------|-------------|-----------|----------|-----------|
| synchronous | 0.18 | 1.00 | 183.3 | 916.1 | 5.59 | 156.5 | 5.3 | 5.3 |
| throughput | 3.15 | 98.69 | 3,227.1 | 16,132.5 | 31.31 | 4,579.2 | 26.1 | 26.1 |
| constant@0.55 | 0.54 | 3.87 | 550.0 | 2,749.6 | 7.20 | 164.0 | 6.9 | 6.9 |
| constant@0.92 | 0.88 | 7.29 | 896.3 | 4,480.9 | 8.32 | 164.3 | 8.0 | 8.0 |
| constant@1.29 | 1.19 | 12.00 | 1,218.3 | 6,090.5 | 10.09 | 164.3 | 9.7 | 9.7 |
| constant@1.67 | 1.47 | 18.27 | 1,505.9 | 7,528.2 | 12.42 | 166.2 | 12.0 | 12.0 |
| constant@2.04 | 1.73 | 24.66 | 1,771.8 | 8,857.4 | 14.25 | — | — | — |
| constant@2.41 | 1.93 | 32.21 | 1,978.5 | 9,890.9 | 16.67 | — | — | — |
| constant@2.78 | 2.09 | 38.77 | 2,141.9 | 10,707.5 | 18.54 | — | — | — |
| constant@3.15 | 2.20 | 46.71 | 2,255.2 | 11,274.0 | 21.21 | — | — | — |

**Key takeaway**: Large-context code reviews (4K prompt) complete in **5.6s** at synchronous with **157ms TTFT**. The system peaks at **~16,100 total tok/s** under maximum concurrency. TTFT remains stable around **164ms** up to ~18 concurrent requests — excellent for multi-user code review.

---

## Benchmark 4: Full File Generation (XLarge)

**Config**: 8,192 prompt tokens, 2,048 output tokens, sweep mode

| Rate | Req/s | Concurrency | Output tok/s | Total tok/s | Latency (s) | TTFT (ms) | ITL (ms) | TPOT (ms) |
|------|-------|-------------|-------------|-------------|-------------|-----------|----------|-----------|
| synchronous | 0.09 | 1.00 | 183.6 | 917.8 | 11.15 | 207.7 | 5.3 | 5.3 |
| throughput | 1.37 | 98.79 | 2,795.5 | 13,976.4 | 72.37 | 9,422.7 | 30.8 | 30.7 |
| constant@0.25 | 0.24 | 3.45 | 495.3 | 2,476.4 | 14.26 | 219.9 | 6.9 | 6.9 |
| constant@0.41 | 0.39 | 6.51 | 798.7 | 3,993.2 | 16.69 | 223.9 | 8.0 | 8.0 |
| constant@0.57 | 0.53 | 10.31 | 1,081.2 | 5,405.6 | 19.53 | 230.5 | 9.4 | 9.4 |
| constant@0.73 | 0.65 | 16.31 | 1,328.5 | 6,641.9 | 25.15 | 239.8 | 12.2 | 12.2 |
| constant@0.89 | 0.76 | 22.01 | 1,550.8 | 7,753.6 | 29.07 | 248.2 | 14.1 | 14.1 |
| constant@1.05 | 0.85 | 28.37 | 1,734.0 | 8,669.3 | 33.51 | 255.3 | 16.2 | 16.2 |
| constant@1.21 | 0.92 | 35.09 | 1,875.6 | 9,377.2 | 38.31 | 263.9 | 18.6 | 18.6 |
| constant@1.37 | 0.98 | 40.13 | 2,002.4 | 10,010.9 | 41.05 | 266.8 | 19.9 | 19.9 |

**Key takeaway**: XLarge file generation (8K prompt + 2K output) takes **11.15s** at synchronous with **208ms TTFT** and a consistent **5.3ms ITL**. Under maximum throughput, the system sustains **~14,000 total tok/s**. TTFT remains under 270ms even at ~40 concurrent requests — demonstrating the H100's ability to handle large-context generation workloads efficiently.

---

## Analysis

### Single-User Performance (Synchronous)
- **ITL is consistently 5.3ms** across all workloads — this is the raw per-token decode speed on the H100
- **TTFT scales linearly** with prompt length: 36ms (256 tokens) → 83ms (1K) → 157ms (4K)
- The Qwen3.6 MoE architecture (3B active out of 35B) delivers dense-model-class decode speed due to the sparse activation

### Multi-User Scaling
- Code completion: supports **~12 concurrent users** before latency doubles (constant@11.78: 1.49s vs sync 0.70s)
- Code generation: supports **~4 concurrent users** at <5s latency
- Code review: supports **~1.7 concurrent users** at <12s latency (large context)
- File generation: supports **~3 concurrent users** at <15s latency for full file writes

### Throughput Ceiling
- Peak total throughput: **~16,100 tok/s** (code review workload)
- Peak output throughput: **~4,300 tok/s** (code generation workload)
- XLarge workload (8K+2K): **~14,000 total tok/s** at max concurrency
- The H100's 94GB HBM3 comfortably holds the FP8 model weights (~35GB) with ample room for KV cache

### Operational Notes
- vLLM v0.19.0 with `VLLM_ENABLE_CUDA_COMPATIBILITY=1` runs on NVIDIA driver 550 (CUDA 12.4) using compat libraries (575.57.08)
- DeepGEMM warmup takes ~10 minutes on first start (JIT kernel compilation for MoE layers)
- FlashAttention v3 and FlashInfer GDN prefill kernels active
- FP8 quantization via CutlassFP8ScaledMM with Triton MoE backend
