# pca-benchmarks

Opt-in [GuideLLM](https://github.com/vllm-project/guidellm) Job that load-tests the live **vLLM LLMIS workload Service** (`qwen3-coder-kserve-workload-svc:8000`, HTTPS with mounted CA — not RHCL / not OpenCode).

## Run (existing OpenShift)

AI serving must already be up. From the repo root:

```bash
# Do not run alongside: make performance (OpenCode ladder) — shared GPU/vLLM
make performance-vllm AI_NAMESPACE=<your-ai-ns>

oc logs -n <your-ai-ns> -f job/guidellm-capacity
```

Values: [`deploy_existing_openshift/values-benchmarks.yaml`](../../deploy_existing_openshift/values-benchmarks.yaml). Chart defaults (streams, workloads) live in [`values.yaml`](values.yaml).

## What it measures

Per code-oriented prompt/output shape:

1. **Concurrent** ladder: streams `1,4,8,16` (≤ `maxRequests` completions per level)
2. **Throughput** probe (optional) — max aggregate tok/s for that shape

Shapes include short completion through near-`--max-model-len` (32K) stress. Failed shapes are non-fatal so cliffs do not abort the Job.

## Results

Stateless Job — capture metrics from **Job logs** (`oc logs -f job/guidellm-capacity`). No PVC.

See [docs/benchmarks.md](../../docs/benchmarks.md).
