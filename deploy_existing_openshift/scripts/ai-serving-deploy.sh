#!/usr/bin/env bash
# Deploy AI serving on existing OpenShift (cold-aware HF_HUB_OFFLINE).
#
# Usage (via Makefile):
#   make ai-serving-deploy-existing-openshift HF_TOKEN=hf_xxx
#
# Cold (no model-cache PVC): deploy with HF_HUB_OFFLINE=0, wait Ready, flip to 1.
# Warm (PVC kept): deploy with HF_HUB_OFFLINE=1 directly (no second restart).
# Override: HF_HUB_OFFLINE=0|1 make ai-serving-deploy-existing-openshift

set -euo pipefail

CHARTS_DIR="${CHARTS_DIR:-charts}"
DEPLOY_VALUES_DIR="${DEPLOY_VALUES_DIR:-deploy_existing_openshift}"
AI_NAMESPACE="${AI_NAMESPACE:-private-assistant-ai-serving}"
HF_TOKEN="${HF_TOKEN:-${HUGGINGFACE_TOKEN:-}}"
MCP_ENABLED="${MCP_ENABLED:-false}"
HELM_ARGS="${HELM_ARGS:-}"
MODEL_NAME="${MODEL_NAME:-qwen3-coder}"
READY_TIMEOUT="${READY_TIMEOUT:-3600s}"
# Optional force: 0|1. Empty = detect from PVC presence.
HF_HUB_OFFLINE_OVERRIDE="${HF_HUB_OFFLINE:-}"

if [[ -z "${HF_TOKEN}" ]]; then
	echo "ERROR: HF_TOKEN is required. Set in .env or pass HF_TOKEN=hf_xxx" >&2
	exit 1
fi

MCP_FLAGS=()
if [[ "${MCP_ENABLED}" == "true" ]]; then
	MCP_FLAGS=(
		--set mcp.enabled=true
		--set pca-mcp.gateway.enabled=false
		--set "pca-mcp.namespace=${AI_NAMESPACE}"
	)
fi

resolve_offline_mode() {
	if [[ "${HF_HUB_OFFLINE_OVERRIDE}" == "0" || "${HF_HUB_OFFLINE_OVERRIDE}" == "1" ]]; then
		echo "${HF_HUB_OFFLINE_OVERRIDE}"
		return
	fi
	if oc get pvc model-cache -n "${AI_NAMESPACE}" &>/dev/null; then
		echo "1"
	else
		echo "0"
	fi
}

wait_serving_ready() {
	local ns="$1" name="$2" timeout="$3"
	echo "==> Waiting for serving Ready (timeout=${timeout}) in ${ns}…"
	if oc get inferenceservice "${name}" -n "${ns}" &>/dev/null; then
		oc wait --for=condition=Ready "inferenceservice/${name}" -n "${ns}" --timeout="${timeout}"
		return
	fi
	if oc get llminferenceservice "${name}" -n "${ns}" &>/dev/null; then
		oc wait --for=condition=Ready "llminferenceservice/${name}" -n "${ns}" --timeout="${timeout}"
		return
	fi
	echo "ERROR: neither InferenceService nor LLMInferenceService/${name} found in ${ns}" >&2
	exit 1
}

OFFLINE_MODE="$(resolve_offline_mode)"
if [[ "${OFFLINE_MODE}" == "1" ]]; then
	echo "==> Warm path: model-cache PVC present (or HF_HUB_OFFLINE=1) → deploy with HF_HUB_OFFLINE=1"
else
	echo "==> Cold path: no model-cache PVC (or HF_HUB_OFFLINE=0) → deploy with HF_HUB_OFFLINE=0, then flip to 1 after Ready"
fi

echo "==> Updating Helm chart dependencies…"
helm dependency update "${CHARTS_DIR}/pca-platform-config"
helm dependency update "${CHARTS_DIR}/pca-ai-serving/charts/pca-observability"
helm dependency update "${CHARTS_DIR}/pca-ai-serving"

echo "==> Deploying platform-config in ${AI_NAMESPACE}…"
helm upgrade --install "${AI_NAMESPACE}-platform-config" "${CHARTS_DIR}/pca-platform-config" \
	--namespace "${AI_NAMESPACE}" --create-namespace \
	-f "${DEPLOY_VALUES_DIR}/values-platform-config.yaml" \
	--set "namespace=${AI_NAMESPACE}" \
	--set "pca-guardrails.namespace=${AI_NAMESPACE}" \
	--set "hfToken.raw=${HF_TOKEN}" \
	"${MCP_FLAGS[@]}"

echo "==> Deploying ai-serving in ${AI_NAMESPACE} (HF_HUB_OFFLINE=${OFFLINE_MODE})…"
# HELM_ARGS unquoted so make-passed flags split; our HF_HUB_OFFLINE --set last wins.
# shellcheck disable=SC2086
helm upgrade --install "${AI_NAMESPACE}-ai-serving" "${CHARTS_DIR}/pca-ai-serving" \
	--namespace "${AI_NAMESPACE}" \
	-f "${DEPLOY_VALUES_DIR}/values-ai-serving.yaml" \
	--set "namespace=${AI_NAMESPACE}" \
	--set "pca-observability.namespace=${AI_NAMESPACE}" \
	${HELM_ARGS} \
	--set "vllm.extraEnv.HF_HUB_OFFLINE=${OFFLINE_MODE}"

if [[ "${OFFLINE_MODE}" == "0" ]]; then
	wait_serving_ready "${AI_NAMESPACE}" "${MODEL_NAME}" "${READY_TIMEOUT}"
	echo "==> Cold bootstrap Ready — flipping HF_HUB_OFFLINE=1 (warm restart rollout follows)…"
	helm upgrade "${AI_NAMESPACE}-ai-serving" "${CHARTS_DIR}/pca-ai-serving" \
		--namespace "${AI_NAMESPACE}" \
		--reuse-values \
		--set vllm.extraEnv.HF_HUB_OFFLINE=1
	echo "==> HF_HUB_OFFLINE=1 applied. Predictor will roll to offline mode (weights stay on model-cache PVC)."
fi

echo "==> AI serving deploy complete (namespace=${AI_NAMESPACE}, HF_HUB_OFFLINE effective path done)."
