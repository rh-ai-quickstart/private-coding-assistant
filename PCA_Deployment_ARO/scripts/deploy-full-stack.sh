#!/usr/bin/env bash
# deploy-full-stack.sh
# Applies all ArgoCD manifests wave-by-wave after ARO cluster + GitOps are ready.
# Waits for operators to install between waves.
#
# Usage: ./deploy-full-stack.sh [ARGOCD_BASE_PATH]
set -euo pipefail

BASE_PATH="${1:-$(dirname "$0")/../argocd}"
BASE_PATH=$(cd "$BASE_PATH" && pwd)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info() { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
step() { echo -e "${CYAN}[STEP]${NC}  $*"; }
error() {
	echo -e "${RED}[ERROR]${NC} $*" >&2
	exit 1
}

oc whoami &>/dev/null || error "Not logged in to OpenShift. Run 'oc login' first."
info "Deploying full PCA stack from: ${BASE_PATH}"
info "Cluster: $(oc whoami --show-server)"

# ── Wave 1a: Operator Subscriptions ──────────────────────────────────────────
step "Wave 1a: Creating operator subscriptions..."
oc apply -f "${BASE_PATH}/01-operators/subscriptions.yaml" 2>&1 | sed 's/^/  /'
oc apply -f "${BASE_PATH}/01-operators/cert-manager.yaml" 2>&1 | sed 's/^/  /' || true
oc apply -f "${BASE_PATH}/01-operators/leader-worker-set.yaml" 2>&1 | sed 's/^/  /' || true

info "Waiting for operator CSVs to reach Succeeded (up to 15 min)..."
for i in $(seq 1 90); do
	SUCCEEDED=$(oc get csv -A --no-headers 2>/dev/null | grep -c "Succeeded" 2>/dev/null) || SUCCEEDED=0
	PENDING=$(oc get csv -A --no-headers 2>/dev/null | grep -c "Pending\|Installing" 2>/dev/null) || PENDING=0

	if [[ ${PENDING} -eq 0 && ${SUCCEEDED} -gt 0 ]]; then
		info "All operators installed: ${SUCCEEDED} CSVs in Succeeded state."
		break
	fi
	echo "  Operators: ${SUCCEEDED} succeeded, ${PENDING} pending (attempt ${i}/90)"
	sleep 10
done

# ── Wave 1b: Operator CRs (require CRDs from installed operators) ────────────
step "Wave 1b: Applying operator custom resources..."
for cr_attempt in $(seq 1 12); do
	FAILED=0
	oc apply -f "${BASE_PATH}/01-operators/nvidia-cluster-policy.yaml" 2>&1 | sed 's/^/  /' || FAILED=1
	oc apply -f "${BASE_PATH}/01-operators/lws-operator-cr.yaml" 2>&1 | sed 's/^/  /' || FAILED=1
	if [[ ${FAILED} == "0" ]]; then
		info "All operator CRs applied successfully."
		break
	fi
	echo "  Some CRDs not ready yet, retrying... (${cr_attempt}/12)"
	sleep 15
done

# ── Wave 2: Platform Config ──────────────────────────────────────────────────
step "Wave 2: Applying platform config (namespaces, RBAC, CheCluster)..."
oc apply -f "${BASE_PATH}/02-platform-config/" 2>&1 | sed 's/^/  /'

info "Waiting for CheCluster to become available..."
for i in $(seq 1 60); do
	CHE_STATUS=$(oc get checluster devspaces -n openshift-devspaces \
		-o jsonpath='{.status.chePhase}' 2>/dev/null || echo "NotReady")
	if [[ ${CHE_STATUS} == "Active" ]]; then
		info "DevSpaces CheCluster is Active."
		break
	fi
	echo "  CheCluster phase: ${CHE_STATUS} (attempt ${i}/60)"
	sleep 15
done

# ── Wave 3: AI Serving ───────────────────────────────────────────────────────
step "Wave 3: Deploying AI serving (LLMInferenceService + llm-d gateway)..."
oc apply -f "${BASE_PATH}/03-ai-serving/" 2>&1 | sed 's/^/  /'

info "Waiting for model to be ready (this can take 10-20 min for model download)..."
for i in $(seq 1 120); do
	MODEL_READY=$(oc get llminferenceservice qwen36-35b -n ai-serving \
		-o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "False")
	if [[ ${MODEL_READY} == "True" ]]; then
		info "Model qwen36-35b is ready and serving."
		break
	fi
	echo "  Model status: not ready yet (attempt ${i}/120)"
	sleep 15
done

# ── Wave 4: DevSpaces ────────────────────────────────────────────────────────
step "Wave 4: Applying DevSpaces config (image build, dashboard samples, extensions)..."
# Apply DevSpaces resources EXCEPT devworkspaces.yaml (which is a template only).
# DevWorkspaces must be created PER USER via setup-devspaces-users.sh so the
# controller.devfile.io/creator label is set correctly for dashboard visibility.
for f in "${BASE_PATH}/04-devspaces/"*.yaml; do
	FNAME=$(basename "$f")
	if [[ ${FNAME} == "devworkspaces.yaml" ]]; then
		echo "  Skipping ${FNAME} (template only — use setup-devspaces-users.sh)"
		continue
	fi
	oc apply -f "$f" 2>&1 | sed 's/^/  /'
done
info "DevSpaces config applied."

echo ""
info "============================================"
info "Full stack deployment complete!"
info "============================================"
info ""
info "Console: $(oc whoami --show-console 2>/dev/null || echo 'N/A')"
info ""
info "Next steps:"
info "  1. Verify GPU node: oc get nodes -l nvidia.com/gpu.present=true"
info "  2. Verify model:    oc get llminferenceservice -n ai-serving"
info "  3. Create users:    ./scripts/setup-devspaces-users.sh"
info "  4. Verify DevSpaces: oc get devworkspace -A"
info "  5. Run GuideLLM:    oc apply -f ${BASE_PATH}/05-benchmarks/guidellm-sweep.yaml"
