#!/usr/bin/env bash
# Remove demo OpenCode/Continue DevSpaces on existing OpenShift.
#
# Usage (via Makefile):
#   DEV_USER=dev-user2  → uninstall that user
#   N=3                 → uninstall dev-user1..dev-user3
#   (neither)           → uninstall every demo user (dev-userN-devspaces)
#
# Only namespaces matching ^dev-user[0-9]+-devspaces$ are touched.
# Personal DevSpaces (e.g. <user>-redhat-com-devspaces-*) are never deleted.
#
# DELETE_NAMESPACE=1 (Makefile default) deletes the user namespace after helm uninstall.

set -euo pipefail

N="${N:-}"
DEV_USER="${DEV_USER:-}"
DELETE_NAMESPACE="${DELETE_NAMESPACE:-1}"

is_demo_ns() {
	[[ $1 =~ ^dev-user[0-9]+-devspaces$ ]]
}

undeploy_one() {
	local user="$1"
	local ns="${user}-devspaces"

	if ! is_demo_ns "$ns"; then
		echo "ERROR: refusing to undeploy '${ns}' (not a demo DevSpace namespace)" >&2
		exit 1
	fi

	if helm status "${ns}-devspaces" -n "$ns" >/dev/null 2>&1; then
		echo "==> helm uninstall ${ns}-devspaces"
		helm uninstall "${ns}-devspaces" --namespace "$ns" --ignore-not-found || true
	else
		echo "==> Helm release ${ns}-devspaces not found (ok)"
	fi

	if [ "$DELETE_NAMESPACE" = "1" ]; then
		echo "==> oc delete namespace ${ns}"
		oc delete namespace "$ns" --ignore-not-found --wait=false
	else
		echo "==> Kept namespace ${ns} (DELETE_NAMESPACE!=1)"
	fi
}

list_live_demo_users() {
	local ns user
	oc get ns -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' |
		grep -E '^dev-user[0-9]+-devspaces$' |
		while read -r ns; do
			user="${ns%-devspaces}"
			echo "$user"
		done
}

if [ -n "$DEV_USER" ] && [ -n "$N" ]; then
	echo "ERROR: pass DEV_USER= or N=, not both" >&2
	exit 1
fi

if [ -n "$DEV_USER" ]; then
	undeploy_one "$DEV_USER"
	exit 0
fi

if [ -n "$N" ]; then
	if ! [[ $N =~ ^[1-9][0-9]*$ ]]; then
		echo "ERROR: N must be a positive integer (got '${N}')" >&2
		exit 1
	fi
	echo "==> Undeploying ${N} DevSpace(s) (dev-user1..dev-user${N})"
	for i in $(seq 1 "$N"); do
		undeploy_one "dev-user${i}"
	done
	exit 0
fi

users=$(list_live_demo_users || true)
if [ -z "$users" ]; then
	echo "==> No demo DevSpace namespaces found (dev-userN-devspaces)"
	exit 0
fi

echo "==> Undeploying all demo DevSpaces"
while read -r user; do
	[ -n "$user" ] || continue
	undeploy_one "$user"
done <<<"$users"
