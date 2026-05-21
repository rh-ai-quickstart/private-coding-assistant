#!/usr/bin/env bash
# validate.sh — Post-deployment validation of all PCA components.
# Run after Terraform + ArgoCD deployment completes.
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; FAILURES=$((FAILURES + 1)); }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

FAILURES=0

echo "========================================="
echo "  PCA Deployment Validation"
echo "========================================="
echo ""

# 1. Operators
echo "--- Checking Operators ---"
for op in "rhods-operator" "devspaces" "servicemeshoperator3" "gpu-operator-certified" "openshift-gitops-operator"; do
  if oc get csv -A 2>/dev/null | grep -q "${op}.*Succeeded"; then
    pass "Operator ${op} installed and healthy"
  else
    fail "Operator ${op} not found or not Succeeded"
  fi
done

# 2. DataScienceCluster
echo ""
echo "--- Checking DataScienceCluster ---"
DSC_MODE=$(oc get datasciencecluster default-dsc -o jsonpath='{.spec.components.kserve.rawDeploymentServiceConfig}' 2>/dev/null || echo "NOT_FOUND")
if [ "$DSC_MODE" = "Headed" ]; then
  pass "DataScienceCluster rawDeploymentServiceConfig = Headed"
else
  fail "DataScienceCluster rawDeploymentServiceConfig = ${DSC_MODE} (expected: Headed)"
fi

# 3. GPU Operator
echo ""
echo "--- Checking GPU Stack ---"
if oc get clusterpolicy gpu-cluster-policy &>/dev/null; then
  pass "NVIDIA ClusterPolicy exists"
else
  warn "NVIDIA ClusterPolicy not found (expected if no GPU nodes)"
fi

# 4. Namespaces
echo ""
echo "--- Checking Namespaces ---"
for ns in "ai-serving" "dev1-devspaces" "dev2-devspaces" "openshift-devspaces"; do
  if oc get ns "${ns}" &>/dev/null; then
    pass "Namespace ${ns} exists"
  else
    fail "Namespace ${ns} missing"
  fi
done

# 5. CheCluster
echo ""
echo "--- Checking Dev Spaces ---"
CHE_STATUS=$(oc get checluster devspaces -n openshift-devspaces -o jsonpath='{.status.chePhase}' 2>/dev/null || echo "NOT_FOUND")
if [ "$CHE_STATUS" = "Active" ]; then
  pass "CheCluster is Active"
else
  fail "CheCluster phase = ${CHE_STATUS} (expected: Active)"
fi

# 6. Model Serving
echo ""
echo "--- Checking Model Serving ---"
LIS_STATUS=$(oc get llminferenceservice qwen3-coder -n ai-serving -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "NOT_FOUND")
if [ "$LIS_STATUS" = "True" ]; then
  pass "LLMInferenceService qwen3-coder is Ready"
else
  warn "LLMInferenceService qwen3-coder Ready = ${LIS_STATUS} (may be starting up)"
fi

# 7. PVC
echo ""
echo "--- Checking Storage ---"
PVC_STATUS=$(oc get pvc model-cache -n ai-serving -o jsonpath='{.status.phase}' 2>/dev/null || echo "NOT_FOUND")
if [ "$PVC_STATUS" = "Bound" ]; then
  pass "PVC model-cache is Bound"
else
  warn "PVC model-cache status = ${PVC_STATUS}"
fi

# 8. Gateway
echo ""
echo "--- Checking llm-d Gateway ---"
GW_STATUS=$(oc get gateway llm-d-gateway -n ai-serving -o jsonpath='{.status.conditions[?(@.type=="Accepted")].status}' 2>/dev/null || echo "NOT_FOUND")
if [ "$GW_STATUS" = "True" ]; then
  pass "llm-d Gateway is Accepted"
else
  warn "llm-d Gateway Accepted = ${GW_STATUS}"
fi

# 9. DevWorkspaces
echo ""
echo "--- Checking DevWorkspaces ---"
for ws in "code-workspace-1:dev1-devspaces" "code-workspace-2:dev2-devspaces"; do
  NAME="${ws%%:*}"
  NS="${ws##*:}"
  WS_PHASE=$(oc get devworkspace "${NAME}" -n "${NS}" -o jsonpath='{.status.phase}' 2>/dev/null || echo "NOT_FOUND")
  if [ "$WS_PHASE" = "Running" ]; then
    pass "DevWorkspace ${NAME} in ${NS} is Running"
  else
    warn "DevWorkspace ${NAME} in ${NS} phase = ${WS_PHASE}"
  fi
done

# 10. ArgoCD Apps
echo ""
echo "--- Checking ArgoCD Applications ---"
for app in "pca-operators" "pca-platform-config" "pca-ai-serving" "pca-devspaces"; do
  SYNC=$(oc get application "${app}" -n openshift-gitops -o jsonpath='{.status.sync.status}' 2>/dev/null || echo "NOT_FOUND")
  HEALTH=$(oc get application "${app}" -n openshift-gitops -o jsonpath='{.status.health.status}' 2>/dev/null || echo "NOT_FOUND")
  if [ "$SYNC" = "Synced" ] && [ "$HEALTH" = "Healthy" ]; then
    pass "ArgoCD app ${app}: Synced + Healthy"
  else
    fail "ArgoCD app ${app}: sync=${SYNC}, health=${HEALTH}"
  fi
done

# 11. Model endpoint connectivity test
echo ""
echo "--- Checking Model Endpoint ---"
ENDPOINT="https://llm-d-gateway-data-science-gateway-class.ai-serving.svc.cluster.local/v1/models"
echo "  Endpoint: ${ENDPOINT}"
echo "  (Run this from within the cluster to test connectivity)"

# Summary
echo ""
echo "========================================="
if [ $FAILURES -eq 0 ]; then
  echo -e "${GREEN}All checks passed!${NC}"
else
  echo -e "${RED}${FAILURES} check(s) failed.${NC}"
fi
echo "========================================="
exit $FAILURES
