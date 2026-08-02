#!/usr/bin/env bash
# Deploy OpenCode/Continue DevSpaces on existing OpenShift.
#
# Usage (via Makefile):
#   N=5                 → sync values + deploy dev-user1..5 in dev-userN-devspaces
#   DEV_USER=dev-user2  → single deploy in dev-user2-devspaces
#
# Namespace is always <DEV_USER>-devspaces (no DEV_NAMESPACE override).

set -euo pipefail

CHARTS_DIR="${CHARTS_DIR:-charts}"
DEPLOY_VALUES_DIR="${DEPLOY_VALUES_DIR:-deploy_existing_openshift}"
AI_NAMESPACE="${AI_NAMESPACE:-private-assistant-ai-serving}"
TYPE="${TYPE:-opencode}"
MCP_ENABLED="${MCP_ENABLED:-false}"
HELM_ARGS="${HELM_ARGS:-}"
N="${N:-}"
DEV_USER="${DEV_USER:-}"
VALUES_PLATFORM="${DEPLOY_VALUES_DIR}/values-platform-config.yaml"

sync_platform_instances() {
	local count="$1"
	if ! command -v yq &>/dev/null; then
		echo "ERROR: yq is required to sync N=${count} into ${VALUES_PLATFORM}" >&2
		exit 1
	fi
	local tmp
	tmp=$(mktemp)
	echo '[]' >"$tmp"
	local i user ns name pass
	for i in $(seq 1 "$count"); do
		user="dev-user${i}"
		ns="${user}-devspaces"
		name="code-workspace-${i}"
		pass="Dev${i}@PCA2026!"
		yq -i \
			". += [{\"namespace\": \"${ns}\", \"name\": \"${name}\", \"user\": \"${user}\", \"password\": \"${pass}\"}]" \
			"$tmp"
	done
	# Replace the committed PLACEHOLDER list entirely.
	yq -i ".devspaces.instances = load(\"${tmp}\")" "$VALUES_PLATFORM"
	rm -f "$tmp"
	echo "==> Overwrote placeholder instances in ${VALUES_PLATFORM} with ${count} user(s) (Dev1@PCA2026! .. Dev${count}@PCA2026!)"
}

deploy_one() {
	local user="$1"
	local ns="${user}-devspaces"
	local global_cfg="$2" # true|false

	if [ "$TYPE" != "opencode" ] && [ "$TYPE" != "continue" ]; then
		echo "ERROR: TYPE must be opencode or continue (got '${TYPE}')" >&2
		exit 1
	fi

	if [ "$TYPE" = "opencode" ]; then
		oc create namespace "$ns" --dry-run=client -o yaml | oc apply -f -
		oc label namespace "$ns" \
			app.kubernetes.io/component=workspaces-namespace \
			app.kubernetes.io/part-of=che.eclipse.org --overwrite
		oc annotate namespace "$ns" \
			che.eclipse.org/username="$user" --overwrite
	fi

	local values_file="${DEPLOY_VALUES_DIR}/values-devspaces.yaml"
	if [ "$TYPE" = "continue" ]; then
		values_file="${DEPLOY_VALUES_DIR}/values-devspaces-continue.yaml"
	fi

	local skip_opencode_build=""
	if [ "$TYPE" != "continue" ]; then
		if oc get buildconfig devspaces-opencode -n opencode-build --no-headers --ignore-not-found 2>/dev/null | grep -q .; then
			skip_opencode_build="--set opencodeBuild.enabled=false"
		fi
	fi

	local mcp_flag=""
	if [ "$MCP_ENABLED" = "true" ]; then
		mcp_flag="--set mcp.enabled=true"
	fi

	local global_flag=""
	if [ "$global_cfg" = "false" ]; then
		global_flag="--set devspacesGlobalConfig.enabled=false"
	fi

	# shellcheck disable=SC2086
	helm upgrade --install "${ns}-devspaces" "${CHARTS_DIR}/pca-devspaces" \
		--namespace "$ns" --create-namespace \
		-f "$values_file" \
		--set "aiServingNamespace=${AI_NAMESPACE}" \
		--set "devspaces[0].user=${user}" \
		${mcp_flag} \
		${global_flag} \
		${HELM_ARGS} \
		${skip_opencode_build}

	echo "==> Deployed DevSpace for ${user} in ${ns}"
}

if [ -n "$N" ]; then
	if ! [[ $N =~ ^[1-9][0-9]*$ ]]; then
		echo "ERROR: N must be a positive integer (got '${N}')" >&2
		exit 1
	fi
	sync_platform_instances "$N"
	echo "==> Deploying ${N} DevSpace(s) (dev-user1..dev-user${N})"
	echo "    Demo passwords: Dev1@PCA2026! .. Dev${N}@PCA2026! — run 'make setup-idp' to apply HTPasswd logins."
	for i in $(seq 1 "$N"); do
		user="dev-user${i}"
		ns="${user}-devspaces"
		global="false"
		if [ "$i" -eq 1 ]; then
			owner=$(oc get configmap vscode-extensions-config -n openshift-devspaces \
				-o jsonpath='{.metadata.annotations.meta\.helm\.sh/release-name}' 2>/dev/null || true)
			if [ -z "$owner" ] || [ "$owner" = "${ns}-devspaces" ]; then
				global="true"
			fi
		fi
		deploy_one "$user" "$global"
	done
	exit 0
fi

if [ -z "$DEV_USER" ]; then
	echo "ERROR: Pass N=<count> or DEV_USER=<username> (e.g. DEV_USER=dev-user1)." >&2
	exit 1
fi

ns="${DEV_USER}-devspaces"
global="true"
owner=$(oc get configmap vscode-extensions-config -n openshift-devspaces \
	-o jsonpath='{.metadata.annotations.meta\.helm\.sh/release-name}' 2>/dev/null || true)
if [ -n "$owner" ] && [ "$owner" != "${ns}-devspaces" ]; then
	global="false"
fi
deploy_one "$DEV_USER" "$global"
