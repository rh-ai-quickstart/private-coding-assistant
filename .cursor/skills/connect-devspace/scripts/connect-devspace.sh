#!/usr/bin/env bash
# Start a PCA DevSpace (if needed), wait until Ready, print OpenCode Web creds + oc rsh.
# Usage: connect-devspace.sh <N|devN|devspace-N|dev-userN>
set -euo pipefail

usage() {
  echo "Usage: $0 <N|devN|devspace-N|dev-userN>" >&2
  echo "  Examples: $0 1 | $0 dev1 | $0 devspace-1 | $0 dev-user1" >&2
  exit 2
}

[[ $# -eq 1 ]] || usage

raw="$1"
case "$raw" in
  ''|*[!0-9]*)
    n="${raw#devspace-}"
    n="${n#dev-user}"
    n="${n#dev}"
    n="${n#-}"
    ;;
  *)
    n="$raw"
    ;;
esac

[[ "$n" =~ ^[0-9]+$ ]] || usage

USERNAME="dev-user${n}"
NS="${USERNAME}-devspaces"
DW="code-workspace-1"
CONTAINER="dev-tools"
POLL_INTERVAL=5
TIMEOUT_SECS=300

die() { echo "ERROR: $*" >&2; exit 1; }
log() { echo "$*" >&2; }

command -v oc >/dev/null 2>&1 || die "oc not found in PATH"
oc whoami >/dev/null 2>&1 || die "not logged in to OpenShift (run: oc login)"

oc get dw "$DW" -n "$NS" >/dev/null 2>&1 || die "DevWorkspace $DW not found in namespace $NS"

dw_id=$(oc get dw "$DW" -n "$NS" -o jsonpath='{.status.devworkspaceId}')
[[ -n "$dw_id" ]] || die "DevWorkspace $DW in $NS has no status.devworkspaceId yet"

phase=$(oc get dw "$DW" -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null || true)
case "$phase" in
  Failed|Error)
    die "DevWorkspace $DW is $phase — fix or recreate before connecting"
    ;;
  Running) ;;
  *)
    log "Starting $DW in $NS (current phase: ${phase:-unknown})..."
    oc patch dw "$DW" -n "$NS" --type merge -p '{"spec":{"started":true}}' >/dev/null
    ;;
esac

# Returns: pod_name|ready_ratio|status  (empty if no matching pod)
find_workspace_pod() {
  oc get pods -n "$NS" --no-headers 2>/dev/null \
    | awk -v id="$dw_id" '
        index($1, id) == 1 {
          print $1 "|" $2 "|" $3
          exit
        }'
}

# True if named container is Ready in the pod
container_ready() {
  local pod="$1" cname="$2"
  local ready
  ready=$(
    oc get pod "$pod" -n "$NS" \
      -o jsonpath="{.status.containerStatuses[?(@.name==\"${cname}\")].ready}" 2>/dev/null || true
  )
  [[ "$ready" == "true" ]]
}

log "Waiting for $DW (id=$dw_id) — phase Running + ${CONTAINER} Ready (timeout ${TIMEOUT_SECS}s)..."
ready_pod=""
start_ts=$(date +%s)
last_msg=""

while true; do
  now=$(date +%s)
  elapsed=$((now - start_ts))
  if ((elapsed >= TIMEOUT_SECS)); then
    die "timed out after ${elapsed}s waiting for $DW in $NS (phase=${phase:-?})"
  fi

  phase=$(oc get dw "$DW" -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null || true)
  case "$phase" in
    Failed|Error)
      die "DevWorkspace entered phase $phase while starting"
      ;;
  esac

  pod_info=$(find_workspace_pod || true)
  pod_name="${pod_info%%|*}"
  rest="${pod_info#*|}"
  ready_ratio="${rest%%|*}"
  pod_status="${rest##*|}"

  msg="  [${elapsed}s] phase=${phase:-?} pod=${pod_name:-none} ${ready_ratio:+ready=$ready_ratio }status=${pod_status:-n/a}"
  if [[ "$msg" != "$last_msg" ]]; then
    log "$msg"
    last_msg="$msg"
  fi

  if [[ "$phase" == "Running" && -n "$pod_name" && "$pod_status" == "Running" ]]; then
    if container_ready "$pod_name" "$CONTAINER"; then
      ready_pod="$pod_name"
      log "Ready in ${elapsed}s: pod=$ready_pod (${CONTAINER} ready)"
      break
    fi
  fi

  sleep "$POLL_INTERVAL"
done

password=$(
  oc get secret opencode-web-password -n "$NS" \
    -o jsonpath='{.data.password}' | base64 -d
) || die "failed to read secret opencode-web-password in $NS"
[[ -n "$password" ]] || die "opencode-web-password secret has empty password"

route_host=$(
  oc get route -n "$NS" -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.host}{"\n"}{end}' \
    | awk '/opencode-web/ { print $2; exit }'
) || true
[[ -n "$route_host" ]] || die "no opencode-web route found in $NS"

rsh_cmd="oc rsh -n ${NS} -c ${CONTAINER} ${ready_pod}"

cat <<EOF
NAMESPACE=${NS}
POD=${ready_pod}
OPENCODE_WEB_URL=https://${route_host}
OPENCODE_USER=opencode
OPENCODE_PASSWORD=${password}
RSH_CMD=${rsh_cmd}
EOF

log ""
log "OpenCode Web: https://${route_host}"
log "Auth: opencode / ${password}"
log "Shell: ${rsh_cmd}"
log "After rsh, run: opencode"
