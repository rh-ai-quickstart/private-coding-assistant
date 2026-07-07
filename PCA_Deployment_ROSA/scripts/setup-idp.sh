#!/usr/bin/env bash
# setup-idp.sh — Configure HTPasswd IDP on an existing OpenShift cluster.
#
# Additively patches the OAuth CR (does not overwrite existing identity providers).
# Reads the user list from a Helm values file.
#
# Usage:
#   ./setup-idp.sh <values-file>
#   ./setup-idp.sh ../../deploy_existing_openshift/values-platform-config.yaml
#
# Prerequisites:
#   - oc (logged in as cluster-admin)
#   - yq (https://github.com/mikefarah/yq)
#   - htpasswd (from httpd-tools / apache2-utils)

set -euo pipefail

VALUES_FILE="${1:?Usage: $0 <values-file>}"
PROVIDER_NAME="pca-htpasswd"
SECRET_NAME="pca-htpass-secret"
SECRET_NS="openshift-config"

if ! command -v yq &>/dev/null; then
	echo "ERROR: yq is required. Install from https://github.com/mikefarah/yq" >&2
	exit 1
fi
if ! command -v htpasswd &>/dev/null; then
	echo "ERROR: htpasswd is required. Install httpd-tools (RHEL) or apache2-utils (Debian)." >&2
	exit 1
fi
if ! oc whoami &>/dev/null; then
	echo "ERROR: Not logged in to OpenShift. Run 'oc login' first." >&2
	exit 1
fi

echo "==> Reading users from ${VALUES_FILE}"
USER_COUNT=$(yq '.users | length' "$VALUES_FILE")
if [ "$USER_COUNT" -eq 0 ]; then
	echo "ERROR: No users found in ${VALUES_FILE}" >&2
	exit 1
fi
echo "    Found ${USER_COUNT} users"

HTPASSWD_FILE=$(mktemp)
trap 'rm -f "$HTPASSWD_FILE"' EXIT

for i in $(seq 0 $((USER_COUNT - 1))); do
	USERNAME=$(yq ".users[$i].username" "$VALUES_FILE")
	PASSWORD=$(yq ".users[$i].password" "$VALUES_FILE")
	if [ -z "$PASSWORD" ] || [ "$PASSWORD" = "null" ]; then
		echo "ERROR: User '${USERNAME}' has no password set in ${VALUES_FILE}" >&2
		exit 1
	fi
	htpasswd -bB "$HTPASSWD_FILE" "$USERNAME" "$PASSWORD"
	echo "    Added user: ${USERNAME}"
done

echo "==> Creating Secret ${SECRET_NAME} in ${SECRET_NS}"
oc create secret generic "$SECRET_NAME" \
	--from-file=htpasswd="$HTPASSWD_FILE" \
	-n "$SECRET_NS" \
	--dry-run=client -o yaml | oc apply -f -

EXISTING=$(oc get oauth cluster -o json |
	yq '.spec.identityProviders // [] | .[] | select(.name == "'"$PROVIDER_NAME"'") | .name')

if [ -n "$EXISTING" ]; then
	echo "==> IDP '${PROVIDER_NAME}' already exists in OAuth CR — updating secret reference"
else
	echo "==> Adding IDP '${PROVIDER_NAME}' to OAuth CR"
	oc patch oauth cluster --type=json -p '[{
    "op": "add",
    "path": "/spec/identityProviders/-",
    "value": {
      "name": "'"$PROVIDER_NAME"'",
      "mappingMethod": "claim",
      "type": "HTPasswd",
      "htpasswd": {
        "fileData": {
          "name": "'"$SECRET_NAME"'"
        }
      }
    }
  }]'
fi

echo "==> Waiting for OAuth pods to restart..."
oc rollout status deployment/oauth-openshift -n openshift-authentication --timeout=120s 2>/dev/null ||
	echo "    OAuth rollout watch timed out — pods may still be restarting"

sleep 5

echo "==> Verifying user logins"
FAILED=0
API_SERVER=$(oc whoami --show-server)
for i in $(seq 0 $((USER_COUNT - 1))); do
	USERNAME=$(yq ".users[$i].username" "$VALUES_FILE")
	PASSWORD=$(yq ".users[$i].password" "$VALUES_FILE")
	if oc login "$API_SERVER" -u "$USERNAME" -p "$PASSWORD" --insecure-skip-tls-verify=true &>/dev/null; then
		echo "    ${USERNAME}: login OK"
	else
		echo "    ${USERNAME}: login FAILED"
		FAILED=1
	fi
done

# Log back in as the original user
oc login "$API_SERVER" --token="$(oc whoami -t 2>/dev/null)" &>/dev/null || true

if [ "$FAILED" -eq 1 ]; then
	echo ""
	echo "WARNING: Some user logins failed. OAuth may still be restarting."
	echo "         Wait 30-60 seconds and retry: oc login -u <username> -p <password>"
	exit 1
fi

echo ""
echo "==> HTPasswd IDP setup complete. ${USER_COUNT} users configured."
