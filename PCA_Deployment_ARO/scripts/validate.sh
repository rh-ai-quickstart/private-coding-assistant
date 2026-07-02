#!/usr/bin/env bash
# validate.sh — Post-deployment validation of all PCA components on ARO.
# Run after Terraform + ArgoCD deployment completes.
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
fail() {
	echo -e "${RED}[FAIL]${NC} $1"
	FAILURES=$((FAILURES + 1))
}
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

FAILURES=0

echo "========================================="
echo "  PCA ARO Deployment Validation"
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

# 3. GPU Operator and A100 nodes
echo ""
echo "--- Checking GPU Stack (NVIDIA A100) ---"
if oc get clusterpolicy gpu-cluster-policy &>/dev/null; then
	pass "NVIDIA ClusterPolicy exists"
else
	warn "NVIDIA ClusterPolicy not found (expected if no GPU nodes)"
fi

GPU_NODES=$(oc get nodes -l nvidia.com/gpu.present=true --no-headers 2>/dev/null | wc -l || echo "0")
if [ "${GPU_NODES}" -gt 0 ]; then
	pass "GPU nodes found: ${GPU_NODES} node(s) with nvidia.com/gpu.present=true"
	oc get nodes -l nvidia.com/gpu.present=true -o custom-columns='NAME:.metadata.name,TYPE:.metadata.labels.node\.kubernetes\.io/instance-type,STATUS:.status.conditions[-1].type' 2>/dev/null || true
else
	warn "No GPU nodes detected yet. MachineSet may still be provisioning."
	warn "Check: oc get machineset -n openshift-machine-api"
fi

# 4. Storage class (Azure managed-csi)
echo ""
echo "--- Checking Storage ---"
if oc get storageclass managed-csi &>/dev/null; then
	pass "StorageClass managed-csi exists"
else
	fail "StorageClass managed-csi not found (required for model-cache PVC)"
fi

PVC_STATUS=$(oc get pvc model-cache -n ai-serving -o jsonpath='{.status.phase}' 2>/dev/null || echo "NOT_FOUND")
if [ "$PVC_STATUS" = "Bound" ]; then
	pass "PVC model-cache is Bound"
else
	warn "PVC model-cache status = ${PVC_STATUS}"
fi

# 5. Namespaces
echo ""
echo "--- Checking Namespaces ---"
for ns in "ai-serving" "dev1-devspaces" "dev2-devspaces" "openshift-devspaces"; do
	if oc get ns "${ns}" &>/dev/null; then
		pass "Namespace ${ns} exists"
	else
		fail "Namespace ${ns} missing"
	fi
done

# 6. CheCluster
echo ""
echo "--- Checking Dev Spaces ---"
CHE_STATUS=$(oc get checluster devspaces -n openshift-devspaces -o jsonpath='{.status.chePhase}' 2>/dev/null || echo "NOT_FOUND")
if [ "$CHE_STATUS" = "Active" ]; then
	pass "CheCluster is Active"
else
	fail "CheCluster phase = ${CHE_STATUS} (expected: Active)"
fi

# 7. Model Serving
echo ""
echo "--- Checking Model Serving ---"
LIS_STATUS=$(oc get llminferenceservice qwen36-35b -n ai-serving -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "NOT_FOUND")
if [ "$LIS_STATUS" = "True" ]; then
	pass "LLMInferenceService qwen36-35b is Ready"
else
	warn "LLMInferenceService qwen36-35b Ready = ${LIS_STATUS} (may be starting up)"
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

# 11. Model endpoint connectivity
echo ""
echo "--- Checking Model Endpoint ---"
GATEWAY_URL="https://llm-d-gateway-data-science-gateway-class.ai-serving.svc.cluster.local"
MODEL_ID=$(oc get inferenceservice -n ai-serving -o jsonpath='{.items[?(@.status.conditions[?(@.type=="Ready")].status=="True")].spec.predictor.model.args[0]}' 2>/dev/null | sed 's/--model=//' || echo "Qwen/Qwen3.6-35B-A3B-FP8")
echo "  Gateway: ${GATEWAY_URL}"
echo "  Model: ${MODEL_ID}"

MODELS_RESULT=$(oc run validate-models --rm -i --restart=Never --image=curlimages/curl -- -sk "${GATEWAY_URL}/v1/models" 2>/dev/null || echo "CONN_FAILED")
if echo "$MODELS_RESULT" | grep -q "${MODEL_ID}"; then
	pass "Model endpoint reachable — ${MODEL_ID} listed"
else
	fail "Model endpoint unreachable or model not listed"
fi

# 12. Tool calling verification
echo ""
echo "--- Checking Tool Calling (reasoning parser + tool parser) ---"
TOOL_RESULT=$(oc run validate-toolcall --rm -i --restart=Never --image=curlimages/curl -- \
	-sk "${GATEWAY_URL}/v1/chat/completions" \
	-H "Content-Type: application/json" \
	-d "{\"model\":\"${MODEL_ID}\",\"messages\":[{\"role\":\"user\",\"content\":\"List files in /tmp\"}],\"tools\":[{\"type\":\"function\",\"function\":{\"name\":\"list_files\",\"description\":\"List directory contents\",\"parameters\":{\"type\":\"object\",\"properties\":{\"path\":{\"type\":\"string\",\"description\":\"Directory path\"}},\"required\":[\"path\"]}}}],\"tool_choice\":\"auto\",\"max_tokens\":200}" 2>/dev/null || echo "TOOL_FAILED")

if echo "$TOOL_RESULT" | grep -q '"finish_reason":"tool_calls"'; then
	pass "Tool calling works — finish_reason=tool_calls"
elif echo "$TOOL_RESULT" | grep -q '"tool_calls":\[{'; then
	pass "Tool calling works — tool_calls array populated"
else
	if echo "$TOOL_RESULT" | grep -q '</think>'; then
		fail "Tool calling broken — </think> tokens leaking into content (missing --reasoning-parser)"
	elif echo "$TOOL_RESULT" | grep -q '<tool_call>'; then
		fail "Tool calling broken — XML tool_call in content (wrong --tool-call-parser, need qwen3_xml)"
	elif echo "$TOOL_RESULT" | grep -q 'TOOL_FAILED'; then
		fail "Tool calling test failed — could not reach gateway"
	else
		warn "Tool calling inconclusive — model may have responded without tool use"
		warn "  Response snippet: $(echo "$TOOL_RESULT" | head -c 200)"
	fi
fi

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
