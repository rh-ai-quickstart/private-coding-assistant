#!/usr/bin/env bash
# Remove PCA on existing OpenShift (AI serving + optional demo DevSpaces).
#
# Usage (via Makefile):
#   make undeploy-existing-openshift
#     full wipe: demo DevSpaces + Helm releases + AI_NAMESPACE (cold next deploy)
#   make ai-serving-undeploy-existing-openshift
#     SKIP_DEVSPACES=1 DELETE_NAMESPACE=0 — helm uninstall only (keep ns + model-cache)
#   make ai-serving-undeploy-existing-openshift DELETE_NAMESPACE=1
#     helm uninstall + delete AI_NAMESPACE
#
# Gateway/maas-default-gateway, Namespace/models-as-a-service, Namespace/kuadrant-system,
# and the Kuadrant CR are annotated helm.sh/resource-policy: keep so helm uninstall
# of the AI-serving release does not delete them.
# Does not delete opencode-build or personal DevSpaces.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AI_NAMESPACE="${AI_NAMESPACE:-private-assistant-ai-serving}"
SKIP_DEVSPACES="${SKIP_DEVSPACES:-0}"
# Full-wipe default; Makefile passes DELETE_NAMESPACE=0 for the warm path.
DELETE_NAMESPACE="${DELETE_NAMESPACE:-1}"

clear_guardrails_finalizers() {
	local ns="$1"
	local name
	name=$(oc get guardrailsorchestrators -n "$ns" -o name --ignore-not-found 2>/dev/null || true)
	if [ -z "$name" ]; then
		return 0
	fi
	echo "==> Clearing GuardrailsOrchestrator finalizers in ${ns}"
	# shellcheck disable=SC2086
	oc patch $name -n "$ns" --type=merge -p '{"metadata":{"finalizers":[]}}' || true
}

if [ "$SKIP_DEVSPACES" != "1" ]; then
	echo "==> Undeploying demo DevSpaces"
	N="${N:-}" DEV_USER="${DEV_USER:-}" DELETE_NAMESPACE=1 \
		"${SCRIPT_DIR}/devspace-undeploy.sh"
fi

echo "==> helm uninstall ${AI_NAMESPACE}-ai-serving"
helm uninstall "${AI_NAMESPACE}-ai-serving" --namespace "${AI_NAMESPACE}" --ignore-not-found || true

echo "==> helm uninstall ${AI_NAMESPACE}-platform-config"
helm uninstall "${AI_NAMESPACE}-platform-config" --namespace "${AI_NAMESPACE}" --ignore-not-found || true

# Group is applied by deploy scripts (not always Helm-owned).
if oc get group pca-developers >/dev/null 2>&1; then
	echo "==> oc delete group pca-developers"
	oc delete group pca-developers --ignore-not-found
fi

if [ "$DELETE_NAMESPACE" = "1" ]; then
	clear_guardrails_finalizers "${AI_NAMESPACE}"
	echo "==> oc delete namespace ${AI_NAMESPACE}"
	oc delete namespace "${AI_NAMESPACE}" --ignore-not-found --wait=false
	echo "==> Waiting for namespace ${AI_NAMESPACE} to terminate"
	if ! oc wait namespace "${AI_NAMESPACE}" --for=delete --timeout=180s 2>/dev/null; then
		if oc get namespace "${AI_NAMESPACE}" >/dev/null 2>&1; then
			echo "==> Namespace still terminating; retrying GuardrailsOrchestrator finalizer"
			clear_guardrails_finalizers "${AI_NAMESPACE}"
			oc wait namespace "${AI_NAMESPACE}" --for=delete --timeout=120s || {
				echo "WARNING: ${AI_NAMESPACE} still present. Check:" >&2
				echo "  oc get namespace ${AI_NAMESPACE} -o jsonpath='{.status.conditions[?(@.type==\"NamespaceContentRemaining\")].message}'" >&2
				exit 1
			}
		fi
	fi
	echo "==> Namespace ${AI_NAMESPACE} deleted (cold next deploy)"
else
	echo "==> Kept namespace ${AI_NAMESPACE} and model-cache PVC (warm path)."
	echo "    Full wipe: make undeploy-existing-openshift"
fi
