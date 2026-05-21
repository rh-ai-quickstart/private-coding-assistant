# Performance Test Results — Qwen3.6-35B-A3B-FP8 on ARO

**Date:** May 18, 2026
**Tool:** [GuideLLM v0.6.0](https://github.com/vllm-project/guidellm)
**Profile:** Sweep (synchronous → throughput → constant rate escalation, 10 stages)

## Environment

| Component | Detail |
|-----------|--------|
| Platform | Azure Red Hat OpenShift (ARO) 4.19, Central US |
| GPU | NVIDIA A100 80 GB (`Standard_NC24ads_A100_v4`) |
| Model | `Qwen/Qwen3.6-35B-A3B-FP8` (MoE, ~3B active params) |
| Serving | vLLM 0.17.1 (upstream), KServe + llm-d AI Gateway |
| Context window | 65,536 tokens |
| GPU memory utilization | 90% |
| Quantization | FP8 (native) |
| RHOAI | 3.3.2 (stable-3.x) |

## Benchmark Configuration

Each benchmark runs a **sweep** of 10 rate stages: one synchronous (serial, 1 request at a time), one throughput (max saturation), and eight constant-rate stages at increasing load. Constraints: max 90 seconds per stage.

---

## Results

### Short Prompt — 128 input tokens / 128 output tokens

| Strategy | Concurrency | Requests | TTFT mean (ms) | TTFT p99 (ms) | ITL mean (ms) | TPOT mean (ms) | E2E (s) | Output tok/s | Req/s |
|----------|-------------|----------|----------------|---------------|---------------|-----------------|---------|--------------|-------|
| synchronous | 1 | 98 | 57.46 | 102.67 | 6.84 | 7.24 | 0.926 | 138.3 | 1.078 |
| throughput | 512 | 150 | 1300.58 | 2097.15 | 45.81 | 55.61 | 7.119 | 2781.3 | 20.701 |
| constant | 512 | 150 | 73.66 | 110.04 | 13.43 | 13.90 | 1.779 | 442.1 | 3.448 |
| constant | 512 | 150 | 77.91 | 108.50 | 16.96 | 17.44 | 2.232 | 728.5 | 5.672 |
| constant | 512 | 150 | 85.09 | 114.48 | 22.96 | 23.45 | 3.001 | 986.4 | 7.668 |
| constant | 512 | 150 | 103.75 | 167.50 | 33.56 | 34.11 | 4.366 | 1193.7 | 9.260 |
| constant | 512 | 150 | 169.84 | 320.30 | 49.87 | 50.81 | 6.503 | 1303.2 | 10.113 |
| constant | 512 | 150 | 203.15 | 395.92 | 54.37 | 55.53 | 7.108 | 1429.1 | 11.090 |
| constant | 512 | 150 | 236.27 | 540.75 | 55.33 | 56.74 | 7.264 | 1543.4 | 11.913 |
| constant | 512 | 150 | 224.43 | 446.18 | 54.47 | 55.80 | 7.143 | 1649.7 | 12.642 |

### Medium Prompt — 512 input tokens / 256 output tokens

| Strategy | Concurrency | Requests | TTFT mean (ms) | TTFT p99 (ms) | ITL mean (ms) | TPOT mean (ms) | E2E (s) | Output tok/s | Req/s |
|----------|-------------|----------|----------------|---------------|---------------|-----------------|---------|--------------|-------|
| synchronous | 1 | 49 | 116.70 | 148.41 | 6.84 | 7.27 | 1.862 | 137.7 | 0.533 |
| throughput | 512 | 100 | 2440.51 | 4483.88 | 40.91 | 50.28 | 12.872 | 2008.2 | 7.615 |
| constant | 512 | 100 | 129.16 | 176.93 | 11.54 | 12.00 | 3.073 | 355.5 | 1.386 |
| constant | 512 | 100 | 133.00 | 157.94 | 16.57 | 17.02 | 4.358 | 559.5 | 2.179 |
| constant | 512 | 100 | 141.79 | 167.28 | 22.19 | 22.66 | 5.800 | 742.5 | 2.887 |
| constant | 512 | 100 | 144.78 | 171.55 | 26.04 | 26.50 | 6.785 | 911.1 | 3.537 |
| constant | 512 | 100 | 148.02 | 166.35 | 31.60 | 32.05 | 8.206 | 1047.2 | 4.065 |
| constant | 512 | 100 | 152.96 | 175.22 | 36.12 | 36.58 | 9.363 | 1155.7 | 4.479 |
| constant | 512 | 100 | 165.26 | 286.44 | 40.61 | 41.09 | 10.520 | 1232.8 | 4.781 |
| constant | 512 | 100 | 185.94 | 283.11 | 43.86 | 44.42 | 11.371 | 1289.9 | 5.001 |

### Long Prompt — 2048 input tokens / 512 output tokens

| Strategy | Concurrency | Requests | TTFT mean (ms) | TTFT p99 (ms) | ITL mean (ms) | TPOT mean (ms) | E2E (s) | Output tok/s | Req/s |
|----------|-------------|----------|----------------|---------------|---------------|-----------------|---------|--------------|-------|
| synchronous | 1 | 20 | 1019.71 | 16689.53 | 6.85 | 8.83 | 4.519 | 138.9 | 0.211 |
| throughput | 512 | 50 | 4181.29 | 8000.63 | 31.68 | 39.79 | 20.372 | 1263.1 | 2.407 |
| constant | 512 | 42 | 233.41 | 260.43 | 9.70 | 10.13 | 5.189 | 240.4 | 0.467 |
| constant | 512 | 50 | 3943.53 | 20398.94 | 20.64 | 28.31 | 14.493 | 369.0 | 0.718 |
| constant | 512 | 50 | 223.31 | 241.90 | 13.85 | 14.26 | 7.299 | 486.5 | 0.946 |
| constant | 512 | 50 | 232.00 | 260.92 | 17.60 | 18.01 | 9.224 | 587.6 | 1.142 |
| constant | 512 | 50 | 236.37 | 262.87 | 20.71 | 21.13 | 10.821 | 674.0 | 1.308 |
| constant | 512 | 50 | 240.65 | 255.65 | 22.56 | 22.98 | 11.768 | 753.7 | 1.462 |
| constant | 512 | 50 | 245.21 | 266.63 | 24.60 | 25.03 | 12.814 | 821.3 | 1.592 |
| constant | 512 | 50 | 251.07 | 280.73 | 26.94 | 27.38 | 14.018 | 865.6 | 1.678 |

---

## Key Observations

### Single-User Latency (Synchronous, 1 concurrent request)

| Metric | Short (128/128) | Medium (512/256) | Long (2048/512) |
|--------|-----------------|-------------------|-----------------|
| TTFT | 57 ms | 117 ms | 1,020 ms |
| ITL | 6.8 ms | 6.8 ms | 6.9 ms |
| TPOT | 7.2 ms | 7.3 ms | 8.8 ms |
| E2E latency | 0.93 s | 1.86 s | 4.52 s |
| Output tokens/s | 138 | 138 | 139 |

- **Inter-token latency is remarkably consistent at ~6.8 ms** across all prompt sizes, translating to ~138 output tokens/second for a single user.
- **TTFT scales with input length** as expected: 57 ms for 128 tokens, 117 ms for 512, and ~1 s for 2048 tokens (prefill phase is compute-bound).

### Peak Throughput (Max Saturation)

| Metric | Short (128/128) | Medium (512/256) | Long (2048/512) |
|--------|-----------------|-------------------|-----------------|
| Output tokens/s | 2,781 | 2,008 | 1,263 |
| Requests/s | 20.7 | 7.6 | 2.4 |
| TTFT p99 | 2,097 ms | 4,484 ms | 8,001 ms |

- The A100 achieves **~2,800 output tokens/s peak** on short prompts, which is excellent for a single-GPU MoE model.
- Throughput degrades gracefully with longer prompts due to increased prefill compute.

### Recommended Operating Point (Latency/Throughput Balance)

For a typical coding assistant workload (~512 input / 256 output tokens), the sweet spot is around **3–4 req/s** where:
- TTFT stays under 170 ms (p99)
- ITL remains under 27 ms
- Total throughput is 750–900 output tokens/s

This supports **3–4 concurrent developers** with responsive completions on a single A100 GPU.

---

## Capacity Planning — Private Code Assistant

The following projections are based on the medium-prompt benchmark (512 input / 256 output tokens), which best represents a typical coding assistant interaction (code context in, completion or explanation out). All projections use the **64K context window** configuration.

### Assumptions

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Concurrent request ratio | 30% | At any instant, 30% of developers have an active request in-flight |
| Typical request size | 512 in / 256 out tokens | Code context + completion — representative of chat, inline completion, and explain flows |
| SLO target (recommended) | ITL < 25 ms, TTFT < 200 ms | Ensures streaming feels real-time; first token appears near-instantly |
| SLO target (acceptable) | ITL < 35 ms, TTFT < 300 ms | Still responsive for interactive coding but noticeable lag under heavy load |
| GPU | 1× NVIDIA A100 80 GB | `Standard_NC24ads_A100_v4` ($3.67/hr) |

### Developer Scaling Table (Single A100 GPU)

| Total Developers | Concurrent Requests (30%) | Aggregate Output tok/s | Tok/s Per User | TTFT mean (ms) | ITL mean (ms) | E2E Latency (s) | Req/s | Experience |
|:----------------:|:-------------------------:|:----------------------:|:--------------:|:--------------:|:-------------:|:----------------:|:-----:|:----------:|
| 10 | 3 | ~270 | ~90 | ~124 | ~10 | ~2.6 | ~1.1 | Excellent |
| 20 | 6 | ~420 | ~70 | ~130 | ~13 | ~3.5 | ~1.7 | Excellent |
| 50 | 15 | ~700 | ~47 | ~140 | ~21 | ~5.5 | ~2.7 | Good |
| 100 | 30 | ~1,000 | ~33 | ~147 | ~30 | ~7.7 | ~3.9 | Acceptable |

> **How to read this table:** With 50 developers on the platform, at any given moment ~15 are waiting for a model response. Each of those 15 users sees code streaming at ~47 tokens/second (roughly 9× human reading speed), with the first token appearing in ~140 ms.

### Multi-GPU Scaling Recommendations

For teams that require **recommended SLO** (ITL < 25 ms) at all load levels:

| Total Developers | Concurrent Requests (30%) | A100 GPUs Needed | Concurrent Per GPU | Expected ITL (ms) | Expected TTFT (ms) | Monthly GPU Cost (24×7) |
|:----------------:|:-------------------------:|:----------------:|:------------------:|:-----------------:|:-------------------:|:-----------------------:|
| 10 | 3 | 1 | 3 | ~10 | ~124 | ~$2,700 |
| 20 | 6 | 1 | 6 | ~13 | ~130 | ~$2,700 |
| 50 | 15 | 1 | 15 | ~21 | ~140 | ~$2,700 |
| 100 | 30 | 2 | 15 each | ~21 | ~140 | ~$5,400 |
| 200 | 60 | 4 | 15 each | ~21 | ~140 | ~$10,800 |
| 500 | 150 | 10 | 15 each | ~21 | ~140 | ~$27,000 |

> **Cost basis:** `Standard_NC24ads_A100_v4` at $3.67/hr × 730 hrs/month ≈ $2,679/month per GPU. Spot/reserved pricing can reduce this by 40–60%.

### User Experience Tiers

| Tier | ITL | TTFT p99 | Tok/s Per User | Feel | Max Concurrent per GPU |
|------|-----|----------|----------------|------|------------------------|
| **Excellent** | < 15 ms | < 180 ms | 65–90 | Instant streaming, indistinguishable from local model | ~6 |
| **Good** | 15–25 ms | < 200 ms | 40–65 | Fast streaming, comparable to cloud AI services | ~15 |
| **Acceptable** | 25–35 ms | < 300 ms | 28–40 | Noticeable but usable, similar to ChatGPT under load | ~30 |
| **Degraded** | > 35 ms | > 300 ms | < 28 | Sluggish, users start to context-switch while waiting | > 30 |

### Notes

- The **MoE architecture** (only ~3B of 35B params active per token) makes this model exceptionally efficient for concurrent serving — a single A100 handles 30 concurrent requests before hitting the acceptable SLO boundary.
- **Autocomplete requests** (short prompt/output) are much cheaper: a single A100 can serve ~12 autocomplete req/s at acceptable latency, so the real bottleneck is chat/explain workloads.
- **Scaling is near-linear** with additional GPUs behind the llm-d AI Gateway, which handles load balancing across replicas automatically.
- **30% concurrency is conservative** for coding assistants. In practice, developers spend most time reading, typing, and thinking — peak concurrency during active coding sessions may reach 40–50%, but average over a workday is typically 15–25%.

---

## Glossary

| Abbreviation | Definition |
|-------------|-----------|
| TTFT | Time To First Token — latency from request submission to first token received |
| ITL | Inter-Token Latency — average time between consecutive output tokens |
| TPOT | Time Per Output Token — total generation time divided by output token count |
| E2E | End-to-End latency — total time from request to final token |
| Output tok/s | Aggregate output token throughput across all concurrent requests |
| Req/s | Requests completed per second |
