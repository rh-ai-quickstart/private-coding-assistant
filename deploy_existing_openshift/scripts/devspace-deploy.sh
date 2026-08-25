#!/usr/bin/env bash
# Deploy OpenCode/Continue DevSpaces on existing OpenShift.
#
# Usage (via Makefile):
#   N=5                 → sync values + deploy dev-user1..5 in dev-userN-devspaces (in parallel)
#   DEV_USER=dev-user2  → single deploy in dev-user2-devspaces
#
# Namespace is always <DEV_USER>-devspaces (no DEV_NAMESPACE override).
#
# Model: N = number of user namespaces / Helm releases (not len(devspaces[])).
# Each release installs one DevWorkspace (values-*.yaml is a single-entry list,
# always overridden at devspaces[0]). Isolation is by namespace; the CR name stays
# code-workspace-1 in every ns.

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
	# Platform instances feed IDP (user/password/namespace). "name" is unused by
	# templates; keep code-workspace-1 to match the per-ns DevWorkspace CR.
	local i user ns pass
	for i in $(seq 1 "$count"); do
		user="dev-user${i}"
		ns="${user}-devspaces"
		pass="Dev${i}@PCA2026!"
		yq -i \
			". += [{\"namespace\": \"${ns}\", \"name\": \"code-workspace-1\", \"user\": \"${user}\", \"password\": \"${pass}\"}]" \
			"$tmp"
	done
	# Replace the committed PLACEHOLDER list entirely.
	yq -i ".devspaces.instances = load(\"${tmp}\")" "$VALUES_PLATFORM"
	rm -f "$tmp"
	echo "==> Overwrote placeholder instances in ${VALUES_PLATFORM} with ${count} user(s) (Dev1@PCA2026! .. Dev${count}@PCA2026!)"
	# Group/pca-developers is rendered by pca-platform-config. Re-helm that
	# release so GitOps and existing OpenShift share one writer. --reuse-values
	# keeps hfToken from the previous install; -f applies the yq'd instances.
	local release="${AI_NAMESPACE}-platform-config"
	if ! helm status "$release" -n "$AI_NAMESPACE" >/dev/null 2>&1; then
		echo "ERROR: Helm release ${release} not found in ${AI_NAMESPACE}. Deploy platform-config first (make ai-serving-deploy-existing-openshift)." >&2
		exit 1
	fi
	helm upgrade "$release" "${CHARTS_DIR}/pca-platform-config" \
		--namespace "$AI_NAMESPACE" \
		--reuse-values \
		-f "$VALUES_PLATFORM" \
		--set "namespace=${AI_NAMESPACE}"
}

# One DevWorkspace per user namespace (separate Helm release). values-*.yaml has a
# single-entry list, so the user override is always devspaces[0] — not an index by N.
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

	# openshift-default Gateways bind TLS to a listener hostname. ClusterIP
	# HTTPS to {gateway}-{class} then fails SSL_ERROR_SYSCALL. Prefer the
	# live listener host unless the caller already set maas.hostname.
	local maas_hostname_flag=""
	if [[ "${HELM_ARGS}" != *maas.hostname* ]]; then
		local live_host
		live_host=$(oc get gateway maas-default-gateway -n openshift-ingress \
			-o jsonpath='{range .spec.listeners[*]}{.hostname}{"\n"}{end}' \
			2>/dev/null | awk 'NF { print; exit }' || true)
		if [ -n "$live_host" ]; then
			maas_hostname_flag="--set maas.hostname=${live_host}"
		fi
	fi

	# shellcheck disable=SC2086
	helm upgrade --install "${ns}-devspaces" "${CHARTS_DIR}/pca-devspaces" \
		--namespace "$ns" --create-namespace \
		-f "$values_file" \
		--set "aiServingNamespace=${AI_NAMESPACE}" \
		--set "devspaces[0].user=${user}" \
		${mcp_flag} \
		${global_flag} \
		${maas_hostname_flag} \
		${HELM_ARGS} \
		${skip_opencode_build}

	echo "==> Deployed DevSpace for ${user} in ${ns}"
}

ensure_pca_developers_user() {
	local user="$1"
	if oc get group pca-developers >/dev/null 2>&1; then
		local users
		users=" $(oc get group pca-developers -o jsonpath='{.users[*]}' 2>/dev/null) "
		if [[ "$users" == *" ${user} "* ]]; then
			return 0
		fi
		oc adm groups add-users pca-developers "$user"
		return 0
	fi
	{
		echo "apiVersion: user.openshift.io/v1"
		echo "kind: Group"
		echo "metadata:"
		echo "  name: pca-developers"
		echo "users:"
		echo "  - \"${user}\""
	} | oc apply -f -
}

# N scales namespaces/releases (dev-user1..N), each with one code-workspace-1 — not
# a multi-entry devspaces[] array in a single release.
if [ -n "$N" ]; then
	if ! [[ $N =~ ^[1-9][0-9]*$ ]]; then
		echo "ERROR: N must be a positive integer (got '${N}')" >&2
		exit 1
	fi
	sync_platform_instances "$N"
	echo "==> Deploying ${N} DevSpace(s) in parallel (dev-user1..dev-user${N})"
	echo "    Demo passwords: Dev1@PCA2026! .. Dev${N}@PCA2026! — run 'make setup-idp' to apply HTPasswd logins."

	log_dir=$(mktemp -d)
	pids=()
	users=()
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
		deploy_one "$user" "$global" >"${log_dir}/${user}.log" 2>&1 &
		pids+=("$!")
		users+=("$user")
	done

	fail=0
	for idx in "${!pids[@]}"; do
		user="${users[$idx]}"
		if wait "${pids[$idx]}"; then
			status="OK"
		else
			status="FAILED"
			fail=1
		fi
		echo "----- ${user} (${status}) -----"
		cat "${log_dir}/${user}.log"
	done
	rm -rf "$log_dir"

	if [ "$fail" -ne 0 ]; then
		echo "ERROR: one or more DevSpace deployments failed (see logs above)" >&2
		exit 1
	fi
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
# MaaSSubscription / MaaSAuthPolicy select Group/pca-developers. N= re-helms
# platform-config (Helm owns the Group). DEV_USER= patches live membership
# until the next N= sync.
ensure_pca_developers_user "$DEV_USER"
deploy_one "$DEV_USER" "$global"
