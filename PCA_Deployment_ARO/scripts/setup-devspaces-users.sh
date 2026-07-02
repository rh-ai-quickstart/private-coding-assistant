#!/usr/bin/env bash
# setup-devspaces-users.sh
#
# Creates HTPasswd users, configures OAuth, and provisions DevWorkspaces
# for each user in their DevSpaces-managed namespace.
#
# CRITICAL: DevSpaces auto-provisions a unique namespace per user when they
# first access the dashboard (pattern: <username>-devspaces-<random>).
# The DevWorkspace controller stamps each workspace with a creator label
# matching the creating user's UID. The dashboard ONLY shows workspaces
# where this label matches the logged-in user. Therefore:
#
#   - Workspaces MUST be created by `oc login` as the actual user
#   - Workspaces MUST be in the DevSpaces auto-provisioned namespace
#   - The opencode-build image-puller RBAC must include the new namespace
#
# Usage:
#   export KUBEADMIN_PASS="<kubeadmin password>"
#   ./setup-devspaces-users.sh
#
# Users are defined in the USERS array below. Edit to add/remove users.
set -euo pipefail

# ── User definitions ──────────────────────────────────────────────────
# Format: "username:password"
USERS=(
	"Dev1:Dev1@PCA2026!"
	"Dev2:Dev2@PCA2026!"
)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="${SCRIPT_DIR}/../argocd/04-devspaces/devworkspaces.yaml"
DEVSPACES_DOMAIN=""
GIT_REPO_URL="https://github.com/manujoy7/Private_AI_Coding_Assistant.git"

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

API_URL=$(oc whoami --show-server 2>/dev/null) || error "Not logged in. Run 'oc login' first."
info "Connected to: ${API_URL}"

# Verify running as cluster-admin
oc auth can-i create oauth --all-namespaces &>/dev/null ||
	error "Must be logged in as cluster-admin (kubeadmin)."

# ── Step 1: Create HTPasswd IDP ───────────────────────────────────────
step "Step 1: Creating HTPasswd identity provider..."

HTPASSWD_FILE=$(mktemp)
trap "rm -f ${HTPASSWD_FILE}" EXIT

FIRST=true
for entry in "${USERS[@]}"; do
	USERNAME="${entry%%:*}"
	PASSWORD="${entry#*:}"
	if $FIRST; then
		htpasswd -cbB "${HTPASSWD_FILE}" "${USERNAME}" "${PASSWORD}"
		FIRST=false
	else
		htpasswd -bB "${HTPASSWD_FILE}" "${USERNAME}" "${PASSWORD}"
	fi
done

oc create secret generic htpass-secret \
	--from-file=htpasswd="${HTPASSWD_FILE}" \
	-n openshift-config \
	--dry-run=client -o yaml | oc apply -f -

oc patch oauth cluster --type=merge -p '{
  "spec": {
    "identityProviders": [
      {
        "name": "htpasswd_provider",
        "mappingMethod": "claim",
        "type": "HTPasswd",
        "htpasswd": {
          "fileData": {
            "name": "htpass-secret"
          }
        }
      }
    ]
  }
}'

info "Waiting for OAuth pods to restart..."
sleep 10
for i in $(seq 1 30); do
	READY=$(oc get pods -n openshift-authentication -l app=oauth-openshift \
		--no-headers 2>/dev/null | grep -c "1/1.*Running" || echo 0)
	if [[ ${READY} -ge 3 ]]; then
		info "OAuth pods ready (${READY}/3)."
		break
	fi
	echo "  OAuth pods ready: ${READY}/3 (${i}/30)"
	sleep 10
done

# ── Step 2: Verify user logins ────────────────────────────────────────
step "Step 2: Verifying user logins..."

for entry in "${USERS[@]}"; do
	USERNAME="${entry%%:*}"
	PASSWORD="${entry#*:}"
	if oc login "${API_URL}" --username="${USERNAME}" --password="${PASSWORD}" \
		--insecure-skip-tls-verify=true &>/dev/null; then
		info "User ${USERNAME} login OK."
	else
		error "User ${USERNAME} login FAILED."
	fi
done

# Switch back to kubeadmin
if [[ -n ${KUBEADMIN_PASS:-} ]]; then
	oc login "${API_URL}" --username=kubeadmin --password="${KUBEADMIN_PASS}" \
		--insecure-skip-tls-verify=true &>/dev/null
else
	warn "KUBEADMIN_PASS not set. Attempting to continue..."
	oc login "${API_URL}" --username=kubeadmin \
		--insecure-skip-tls-verify=true &>/dev/null 2>&1 || true
fi

# ── Step 3: Trigger DevSpaces namespace provisioning ──────────────────
step "Step 3: Triggering DevSpaces namespace provisioning..."

DEVSPACES_ROUTE=$(oc get route devspaces -n openshift-devspaces \
	-o jsonpath='{.spec.host}' 2>/dev/null || echo "")
if [[ -z ${DEVSPACES_ROUTE} ]]; then
	DEVSPACES_ROUTE=$(oc get checluster devspaces -n openshift-devspaces \
		-o jsonpath='{.status.cheURL}' 2>/dev/null | sed 's|https://||')
fi

for entry in "${USERS[@]}"; do
	USERNAME="${entry%%:*}"
	PASSWORD="${entry#*:}"

	# Login as user and hit DevSpaces API to trigger namespace provisioning
	oc login "${API_URL}" --username="${USERNAME}" --password="${PASSWORD}" \
		--insecure-skip-tls-verify=true &>/dev/null
	TOKEN=$(oc whoami -t)

	curl -sk "https://${DEVSPACES_ROUTE}/api/kubernetes/namespace" \
		-H "Authorization: Bearer ${TOKEN}" &>/dev/null || true

	info "Triggered namespace provisioning for ${USERNAME}."
	sleep 3
done

# Switch back to kubeadmin
if [[ -n ${KUBEADMIN_PASS:-} ]]; then
	oc login "${API_URL}" --username=kubeadmin --password="${KUBEADMIN_PASS}" \
		--insecure-skip-tls-verify=true &>/dev/null
fi

# Wait for namespaces to appear
info "Waiting for DevSpaces namespaces to be provisioned..."
sleep 10

# ── Step 4: Discover namespaces and create workspaces ─────────────────
step "Step 4: Creating workspaces in DevSpaces-managed namespaces..."

for entry in "${USERS[@]}"; do
	USERNAME="${entry%%:*}"
	PASSWORD="${entry#*:}"
	USERNAME_LOWER=$(echo "${USERNAME}" | tr '[:upper:]' '[:lower:]')

	# Find the DevSpaces-managed namespace for this user
	USER_NS=$(oc get ns -l app.kubernetes.io/component=workspaces-namespace \
		-o jsonpath="{range .items[*]}{.metadata.name}{'\t'}{.metadata.annotations.che\.eclipse\.org/username}{'\n'}{end}" \
		2>/dev/null | grep -i "	${USERNAME}$" | awk '{print $1}' | head -1)

	if [[ -z ${USER_NS} ]]; then
		warn "No DevSpaces namespace found for ${USERNAME}. Creating one manually..."
		RAND=$(head -c 3 /dev/urandom | xxd -p | head -c 6)
		USER_NS="${USERNAME_LOWER}-devspaces-${RAND}"
		cat <<NSEOF | oc apply -f -
apiVersion: v1
kind: Namespace
metadata:
  name: ${USER_NS}
  annotations:
    che.eclipse.org/username: ${USERNAME}
  labels:
    app.kubernetes.io/component: workspaces-namespace
    app.kubernetes.io/part-of: che.eclipse.org
NSEOF
		# Grant admin to the user
		oc create rolebinding "${USERNAME_LOWER}-admin" \
			--clusterrole=admin --user="${USERNAME}" -n "${USER_NS}" 2>/dev/null || true
	fi

	info "User ${USERNAME} → namespace ${USER_NS}"

	# Grant image-puller for the custom OpenCode image
	oc policy add-role-to-group system:image-puller \
		"system:serviceaccounts:${USER_NS}" \
		--namespace=opencode-build 2>/dev/null || true

	# Login as the user and create the workspace
	oc login "${API_URL}" --username="${USERNAME}" --password="${PASSWORD}" \
		--insecure-skip-tls-verify=true &>/dev/null

	cat <<WSEOF | oc apply -f -
apiVersion: workspace.devfile.io/v1alpha2
kind: DevWorkspace
metadata:
  name: opencode-${USERNAME_LOWER}
  namespace: ${USER_NS}
  labels:
    che.eclipse.org/devworkspace: "true"
  annotations:
    che.eclipse.org/devfile-source: |
      factory:
        params: url=${GIT_REPO_URL}
spec:
  started: true
  routingClass: che
  contributions:
    - name: editor
      uri: "https://eclipse-che.github.io/che-plugin-registry/main/v3/plugins/che-incubator/che-code/latest/devfile.yaml"
  template:
    projects:
      - name: private-ai-coding-assistant
        git:
          remotes:
            origin: ${GIT_REPO_URL}
    components:
      - name: dev-tools
        container:
          image: image-registry.openshift-image-registry.svc:5000/opencode-build/devspaces-opencode:latest
          memoryLimit: 8Gi
          memoryRequest: 1Gi
          cpuLimit: "4000m"
          cpuRequest: 500m
          mountSources: true
          env:
            - name: VLLM_ENDPOINT
              value: "https://llm-d-gateway-data-science-gateway-class.ai-serving.svc.cluster.local/v1"
            - name: VLLM_MODEL_ID
              value: "Qwen/Qwen3.6-35B-A3B-FP8"
            - name: OPENAI_API_KEY
              value: "EMPTY"
            - name: OPENAI_BASE_URL
              value: "https://llm-d-gateway-data-science-gateway-class.ai-serving.svc.cluster.local/v1"
            - name: NODE_TLS_REJECT_UNAUTHORIZED
              value: "0"
            - name: OPENCODE_SERVER_PASSWORD
              value: "${PASSWORD}"
            - name: DEFAULT_EXTENSIONS
              value: "/tmp/opencode-ext/sst-dev.opencode.vsix"
          endpoints:
            - name: opencode-web
              targetPort: 4096
              exposure: public
              protocol: https
              attributes:
                cookiesAuthEnabled: true
    commands:
      - id: download-opencode-extension
        exec:
          component: dev-tools
          commandLine: |
            mkdir -p /tmp/opencode-ext
            curl -fsSL "https://open-vsx.org/api/sst-dev/opencode/latest/file/sst-dev.opencode-0.0.13.vsix" \
              --location -o /tmp/opencode-ext/sst-dev.opencode.vsix
            echo "OpenCode extension downloaded"
          label: "Download OpenCode Extension"
      - id: start-opencode-web
        exec:
          component: dev-tools
          commandLine: |
            nohup opencode web --port 4096 --hostname 0.0.0.0 > /tmp/opencode-web.log 2>&1 &
            echo "OpenCode Web UI started on port 4096"
          label: "Start OpenCode Web UI"
    events:
      postStart:
        - download-opencode-extension
        - start-opencode-web
WSEOF

	info "Workspace opencode-${USERNAME_LOWER} created in ${USER_NS}."
done

# Switch back to kubeadmin
if [[ -n ${KUBEADMIN_PASS:-} ]]; then
	oc login "${API_URL}" --username=kubeadmin --password="${KUBEADMIN_PASS}" \
		--insecure-skip-tls-verify=true &>/dev/null
fi

# ── Step 5: Wait for workspaces ───────────────────────────────────────
step "Step 5: Waiting for workspaces to start..."

for entry in "${USERS[@]}"; do
	USERNAME="${entry%%:*}"
	USERNAME_LOWER=$(echo "${USERNAME}" | tr '[:upper:]' '[:lower:]')
	USER_NS=$(oc get ns -l app.kubernetes.io/component=workspaces-namespace \
		-o jsonpath="{range .items[*]}{.metadata.name}{'\t'}{.metadata.annotations.che\.eclipse\.org/username}{'\n'}{end}" \
		2>/dev/null | grep -i "	${USERNAME}$" | awk '{print $1}' | head -1)

	for i in $(seq 1 30); do
		STATUS=$(oc get devworkspace "opencode-${USERNAME_LOWER}" -n "${USER_NS}" \
			-o jsonpath='{.status.phase}' 2>/dev/null || echo "Unknown")
		if [[ ${STATUS} == "Running" ]]; then
			URL=$(oc get devworkspace "opencode-${USERNAME_LOWER}" -n "${USER_NS}" \
				-o jsonpath='{.status.mainUrl}' 2>/dev/null)
			info "${USERNAME}: Running → ${URL}"
			break
		fi
		echo "  ${USERNAME}: ${STATUS} (${i}/30)"
		sleep 10
	done
done

echo ""
info "═══════════════════════════════════════════════════════"
info " DevSpaces User Setup Complete"
info "═══════════════════════════════════════════════════════"
echo ""
DASHBOARD=$(oc get checluster devspaces -n openshift-devspaces \
	-o jsonpath='{.status.cheURL}' 2>/dev/null || echo "https://devspaces.<cluster-domain>")
info "Dashboard: ${DASHBOARD}"
echo ""
for entry in "${USERS[@]}"; do
	USERNAME="${entry%%:*}"
	PASSWORD="${entry#*:}"
	info "  ${USERNAME} / ${PASSWORD}"
done
echo ""
info "Factory URL (users can also create workspaces by opening this in their browser):"
info "  ${DASHBOARD}/#${GIT_REPO_URL}"
echo ""
info "Both VS Code extension (Ctrl+Esc) and Web UI (port 4096) are available."
