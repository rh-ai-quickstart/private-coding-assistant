# Qwen3.8-27B-FP8 vs Qwen3.6-35B-A3B-FP8 — model variant rationale

Background for the `model.variant` / `model_variant` selector (see
[models-and-hardware.md](models-and-hardware.md)). Documents why Qwen3.8 isn't a drop-in swap for
Qwen3.6 and what the chart's `qwen3.8` preset overrides to account for it.

## Why this isn't a drop-in swap

| | Qwen3.6-35B-A3B-FP8 | Qwen3.8-27B-FP8 |
|---|---|---|
| Type | Sparse MoE — 35B total / **3B active**/token | **Dense** — 27B active/token (all params) |
| Layers | 40 (10 full-attention + 30 linear-attention, 1-in-4) | 64 (16 full-attention + 48 linear-attention, 1-in-4) |
| Full-attn KV heads × head dim | 2 × 256 | 4 × 256 |
| Modality | Text-only | Native vision-language (text serving is what's verified in vLLM today) |
| Native context | 262,144 | 262,144 (same) |
| FP8 weight footprint | ~35 GB | ~30.9 GB |
| License | Custom (Qwen) | Apache 2.0 |
| vLLM architecture class | `Qwen3_5_moe_text` | `Qwen3_5ForConditionalGeneration` / `Qwen3_5_text` |

Two effects compound and don't show up in the FP8 file-size comparison:

- **~3.2x more KV-cache bytes per token of context** (more full-attention layers, each wider).
- **~9x more active compute per token** (dense 27B vs MoE's ~3B active) — drives decode
  throughput down, independent of the KV-cache effect.

Net: capacity at a 32K context is roughly comparable between the two; at 200K+ context, expect a
single GPU to hold roughly 1/3 the concurrent long-context sessions it holds with Qwen3.6, and
each session responds slower due to the compute difference. Re-run `make performance-vllm` after
switching `model.variant` — Qwen3.6 benchmark numbers do not carry over to Qwen3.8.

## What the `qwen3.8` preset changes

Implemented in `charts/pca-ai-serving/templates/_helpers.tpl`. Only one variant is deployed at a
time — see `model_variant`'s description in `PCA_Deployment_ROSA/ARO/terraform/variables.tf` for
why concurrent serving of both isn't supported.

1. **vLLM image**: bumped to `vllm/vllm-openai:v0.27.0`+ — Qwen3.5-architecture support (which
   Qwen3.8-27B reuses) landed in v0.27.0 (2026-08-10 vLLM release, "Qwen3.5 text-only dense and MoE
   models"). Also requires `transformers >= 5.8.0` in that image, per vLLM's own recipe
   (`recipes.vllm.ai/Qwen/Qwen3.8-27B`).
2. **Model ID**: `Qwen/Qwen3.8-27B-FP8`, kept in sync across `pca-ai-serving.model.id` and
   `pca-devspaces.modelId` per the existing rule in `models-and-hardware.md`.
3. **Tool call parser**: `qwen3_xml` → `qwen3_coder`, per vLLM's official serving recipe
   (`--tool-call-parser qwen3_coder --reasoning-parser qwen3`).
4. **`--max-num-seqs=128`**: Qwen3.6's `extraArgs` (batched-token/cudagraph tuning) are
   Mamba/MoE-specific and don't apply to Qwen3.8's dense architecture; the dense preset instead
   caps `max-num-seqs` to stay within available Mamba-free KV cache blocks at this GPU's memory
   budget.
5. **`gpuMemoryUtilization: 0.92`**: re-tuned headroom for Qwen3.8's larger activation memory vs.
   Qwen3.6's tuned `0.90`.

No hardware change is required for either variant — both ROSA (`g6e.2xlarge`, L40S 48GB) and ARO
(`Standard_NC40ads_H100_v5`, H100 NVL 94GB) already run single-GPU/TP1, which fits both FP8
checkpoints.

Not wired into the chart today (future work, not needed for either preset to function):
multimodal input (Qwen3.8 has a vision config; vLLM's recipe and this chart both serve text-only),
context length beyond 32K (both models natively support up to 262,144), and graduated
`reasoning_effort` control (chart exposes only on/off via `vllm.enableThinking`).

## Sources

- [Qwen/Qwen3.8-27B config.json](https://huggingface.co/Qwen/Qwen3.8-27B/blob/main/config.json)
- [Qwen/Qwen3.6-35B-A3B model card](https://huggingface.co/Qwen/Qwen3.6-35B-A3B)
- [vLLM Recipes: Qwen3.8-27B](https://recipes.vllm.ai/Qwen/Qwen3.8-27B)
- [vLLM v0.27.0 release notes](https://github.com/vllm-project/vllm/releases/tag/v0.27.0)
- [vLLM blog: Day 0 support for Qwen3.8 family](https://vllm.ai/blog/2026-08-12-qwen3.8)
