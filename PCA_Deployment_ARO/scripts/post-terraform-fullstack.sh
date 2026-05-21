#!/usr/bin/env bash
# post-terraform-fullstack.sh
# Run this AFTER Terraform apply completes.
# Deploys the full PCA stack, waits for model readiness, runs GuideLLM sweep,
# and extracts results to testresults_h100.md.
#
# Usage: ./post-terraform-fullstack.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_PATH="${SCRIPT_DIR}/../argocd"
RESULTS_FILE="${SCRIPT_DIR}/../../testresults_h100.md"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
step()  { echo -e "${CYAN}[STEP]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

oc whoami &>/dev/null || error "Not logged in to OpenShift. Run 'oc login' first."
info "Connected to: $(oc whoami --show-server)"

# ── Step 1: Deploy full stack ──────────────────────────────────────────
step "Step 1: Deploying full PCA stack..."
chmod +x "${SCRIPT_DIR}/deploy-full-stack.sh"
"${SCRIPT_DIR}/deploy-full-stack.sh" "${BASE_PATH}"

# ── Step 2: Wait for GPU node to be ready ──────────────────────────────
step "Step 2: Waiting for H100 GPU node..."
for i in $(seq 1 90); do
  GPU_NODES=$(oc get nodes -l nvidia.com/gpu.present=true --no-headers 2>/dev/null | wc -l | tr -d ' ')
  if [[ "${GPU_NODES}" -ge 1 ]]; then
    info "H100 GPU node is ready."
    oc get nodes -l nvidia.com/gpu.present=true
    break
  fi
  echo "  Waiting for GPU node... (${i}/90)"
  sleep 20
done

# ── Step 3: Ensure model is serving ───────────────────────────────────
step "Step 3: Waiting for Qwen model to be fully serving..."
for i in $(seq 1 120); do
  MODEL_READY=$(oc get llminferenceservice qwen36-35b -n ai-serving \
    -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "False")
  if [[ "${MODEL_READY}" == "True" ]]; then
    info "Model qwen36-35b is ready and serving."
    break
  fi
  echo "  Model status: not ready (${i}/120)"
  sleep 15
done

# ── Step 4: Run GuideLLM sweep ────────────────────────────────────────
step "Step 4: Running GuideLLM benchmark sweep..."
oc apply -f "${BASE_PATH}/05-benchmarks/guidellm-sweep.yaml"

info "Waiting for GuideLLM job to complete (this takes 15-30 min)..."
oc wait --for=condition=Complete job/guidellm-sweep-h100 -n ai-serving --timeout=3600s 2>/dev/null || {
  warn "GuideLLM job timed out or failed. Checking status..."
  oc get job guidellm-sweep-h100 -n ai-serving
  oc get pods -n ai-serving -l app=guidellm
}

# ── Step 5: Extract results ───────────────────────────────────────────
step "Step 5: Extracting GuideLLM results..."
GUIDELLM_POD=$(oc get pods -n ai-serving -l app=guidellm --sort-by='.metadata.creationTimestamp' \
  -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null || echo "")

if [[ -z "${GUIDELLM_POD}" ]]; then
  warn "No GuideLLM pod found. Results extraction skipped."
  exit 0
fi

info "Extracting logs from pod: ${GUIDELLM_POD}"
LOGS=$(oc logs "${GUIDELLM_POD}" -n ai-serving 2>/dev/null || echo "Failed to get logs")

cat > "${RESULTS_FILE}" << HEADER
# GuideLLM Benchmark Results — NVIDIA H100 NVL 94 GB
> Generated: $(date -u '+%Y-%m-%d %H:%M UTC')
> Cluster: aro-pca-aue (Australia East)
> GPU: Standard_NC40ads_H100_v5 (1x H100 NVL, 94 GB HBM3)
> Model: Qwen/Qwen3.6-35B-A3B-FP8 (MoE, ~3B active params)
> Platform: ARO 4.20.15 / RHOAI fast-3.x / vLLM + llm-d gateway

## Benchmark Configuration

| Benchmark | Prompt Tokens | Output Tokens | Duration |
|-----------|--------------|---------------|----------|
| code-completion-short | 256 | 128 | 120s |
| code-generation-medium | 1024 | 512 | 180s |
| code-review-large | 4096 | 1024 | 300s |
| file-generation-xlarge | 8192 | 2048 | 360s |

## Raw Output

\`\`\`
${LOGS}
\`\`\`

## Key Metrics Summary

| Metric | Description |
|--------|-------------|
| tokens_per_second | Total throughput (prompt + output) |
| output_tokens_per_second | Generation throughput |
| time_to_first_token_ms | TTFT latency |
| inter_token_latency_ms | ITL per token |
| request_latency | End-to-end request time |
| requests_per_second | Throughput at various concurrency levels |

---
*Results extracted from GuideLLM sweep job on ARO cluster aro-pca-aue.*
HEADER

info "Results written to: ${RESULTS_FILE}"
info "Done!"
