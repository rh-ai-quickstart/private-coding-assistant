#!/usr/bin/env bash
# Drive the deployed PCA stack the way a user does: in-cluster OpenAI-compatible HTTP.
# Usage: verify-pca.sh <doctor|models|chat|http|grafana-health|devspace-status|opencode-chat|cleanup> [args]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/../../.." && pwd)"

AI_NAMESPACE="${AI_NAMESPACE:-private-assistant-ai-serving}"
LLMIS_NAME="${LLMIS_NAME:-qwen3-coder}"
GATEWAY_CLASS="data-science-gateway-class"
LLMD_GATEWAY="llm-d-gateway"
AI_GATEWAY="pca-ai-gateway"
APIKEY_SECRET="pca-ai-gw-apikey"
APIKEY_KEY="api_key"
CURL_IMAGE="${CURL_IMAGE:-curlimages/curl:8.5.0}"
VIA="${VIA:-gateway}"

RUN_ID="${RUN_ID:-v$(date +%Y%m%d%H%M%S)}"
EVIDENCE_DIR="${EVIDENCE_DIR:-$SKILL_DIR/artifacts/$RUN_ID}"

usage() {
	cat <<EOF
Usage: $0 <command> [args]

Commands:
  doctor              Read-only health (AI serving if allowed; else this user's DevSpace)
  models              GET /v1/models (VIA=gateway|llmd)
  chat                POST /v1/chat/completions (VIA=gateway|llmd|opencode)
  http METHOD URL     Raw in-cluster HTTP (curl pod in AI_NAMESPACE)
  grafana-health      GET Grafana /api/health
  devspace-status     Read-only DevWorkspace / OpenCode route (needs DEV_USER)
  opencode-chat       OpenCode Web API via port-forward (same path as tests/e2e)
  cleanup             Delete curl pods this RUN_ID created (keeps evidence)

Env:
  AI_NAMESPACE   default private-assistant-ai-serving
  DEV_USER       maps to DEV_NAMESPACE=<user>-devspaces; inferred from oc whoami
                 when <whoami>-devspaces exists
  DEV_NAMESPACE  override DevSpaces namespace
  VIA            gateway (RHCL), llmd, or opencode
  RUN_ID         evidence + pod label (lowercase DNS-safe)
  EVIDENCE_DIR   default .cursor/skills/verify-pca/artifacts/\$RUN_ID
  PROMPT         chat user text (default includes RUN_ID token)
  MAX_TOKENS     default 32
  MODEL_ID       override; else LLMInferenceService spec.model.name
  EXPECT         opencode-chat: clean (default) or block (guardrails secret)

Examples (repo root, host oc — not inside the provisioner container):
  .cursor/skills/verify-pca/scripts/verify-pca.sh doctor
  DEV_USER=dev-user1 .cursor/skills/verify-pca/scripts/verify-pca.sh chat
  VIA=opencode .cursor/skills/verify-pca/scripts/verify-pca.sh chat
  VIA=llmd .cursor/skills/verify-pca/scripts/verify-pca.sh models
  .cursor/skills/verify-pca/scripts/verify-pca.sh cleanup
EOF
}

die() {
	echo "ERROR: $*" >&2
	exit 1
}

log() { echo "$*" >&2; }

ensure_evidence() {
	mkdir -p "$EVIDENCE_DIR"
}

dev_namespace() {
	if [[ -n ${DEV_NAMESPACE:-} ]]; then
		echo "$DEV_NAMESPACE"
		return
	fi
	if [[ -n ${DEV_USER:-} ]]; then
		echo "${DEV_USER}-devspaces"
		return
	fi
	echo ""
}

need_oc() {
	command -v oc >/dev/null 2>&1 || die "oc not found in PATH (run on the host, not inside the provisioner container)"
}

need_login() {
	need_oc
	local who
	if ! who=$(oc whoami 2>/dev/null); then
		die "not logged in to OpenShift (run: oc login). Do not helm-deploy as a substitute."
	fi
	OC_USER="$who"
	infer_dev_user
}

# If DEV_USER/DEV_NAMESPACE unset and <whoami>-devspaces exists, use that user
# (same mapping as tests/e2e: DEV_USER → <user>-devspaces).
infer_dev_user() {
	if [[ -n ${DEV_USER:-} || -n ${DEV_NAMESPACE:-} ]]; then
		return
	fi
	[[ -n ${OC_USER:-} ]] || return
	if oc get namespace "${OC_USER}-devspaces" >/dev/null 2>&1; then
		DEV_USER="$OC_USER"
		log "DEV_USER inferred from oc whoami: $DEV_USER"
	fi
}

# ok | forbidden | missing
ai_namespace_access() {
	local out rc=0
	out=$(oc get namespace "$AI_NAMESPACE" -o name 2>&1) || rc=$?
	if [[ $rc -eq 0 ]]; then
		echo ok
		return
	fi
	if grep -qiE 'forbidden|cannot get resource|cannot list resource' <<<"$out"; then
		echo forbidden
		return
	fi
	echo missing
}

ide_base_url_from_dw() {
	local ns="$1" dw="${2:-code-workspace-1}" json
	json=$(oc get dw "$dw" -n "$ns" -o json 2>/dev/null) || {
		echo ""
		return 0
	}
	printf '%s' "$json" | python3 -c '
import json, sys
obj = json.load(sys.stdin)
found = []

def walk(o):
    if isinstance(o, dict):
        if o.get("name") == "OPENAI_BASE_URL" and "value" in o:
            found.append(str(o.get("value") or ""))
        for v in o.values():
            walk(v)
    elif isinstance(o, list):
        for v in o:
            walk(v)

walk(obj)
print(found[0] if found else "")
'
}

ide_via_from_url() {
	local url="$1"
	if [[ $url == *guardrails-proxy* ]]; then
		echo guardrails
	elif [[ $url == *pca-ai-gateway* ]]; then
		echo gateway
	elif [[ $url == *llm-d-gateway* ]]; then
		echo llmd
	elif [[ -n $url ]]; then
		echo other
	else
		echo unset
	fi
}

llmd_v1() {
	echo "https://${LLMD_GATEWAY}-${GATEWAY_CLASS}.${AI_NAMESPACE}.svc.cluster.local/v1"
}

ai_gw_v1() {
	echo "https://${AI_GATEWAY}-${GATEWAY_CLASS}.${AI_NAMESPACE}.svc.cluster.local/v1"
}

via_v1() {
	case "$VIA" in
	gateway) ai_gw_v1 ;;
	llmd) llmd_v1 ;;
	*) die "VIA must be gateway or llmd (got ${VIA})" ;;
	esac
}

condition_status() {
	local resource="$1" name="$2" ctype="$3" json
	json=$(oc get "$resource" "$name" -n "$AI_NAMESPACE" -o json 2>/dev/null) || {
		echo ""
		return 0
	}
	printf '%s' "$json" | python3 -c '
import json, sys
want = sys.argv[1]
obj = json.load(sys.stdin)
for c in (obj.get("status") or {}).get("conditions") or []:
    if c.get("type") == want:
        print(c.get("status") or "")
        break
' "$ctype"
}

model_id() {
	if [[ -n ${MODEL_ID:-} ]]; then
		echo "$MODEL_ID"
		return
	fi
	local name
	name=$(oc get llminferenceservice "$LLMIS_NAME" -n "$AI_NAMESPACE" \
		-o jsonpath='{.spec.model.name}' 2>/dev/null || true)
	if [[ -n $name ]]; then
		echo "$name"
	else
		echo "Qwen/Qwen3.6-35B-A3B-FP8"
	fi
}

apikey() {
	local ns
	ns=$(dev_namespace)
	[[ -n $ns ]] || die "gateway auth needs DEV_USER or DEV_NAMESPACE"
	oc get secret "$APIKEY_SECRET" -n "$ns" -o jsonpath="{.data.${APIKEY_KEY}}" |
		base64 -d
}

# in_cluster_http METHOD URL [timeout_secs]
# Optional: HTTP_HEADERS (bash array), HTTP_BODY_FILE, HTTP_INSECURE=1, HTTP_OUT
in_cluster_http() {
	local method="$1" url="$2" timeout="${3:-60}"
	local insecure="${HTTP_INSECURE:-1}"
	ensure_evidence
	need_login

	local -a curl_parts=(
		curl -sS -o /tmp/body -w '%{http_code}'
		--max-time "$timeout"
		-X "$method" "$url"
	)
	if [[ $insecure == 1 ]]; then
		curl_parts+=(-k)
	fi
	local h
	for h in "${HTTP_HEADERS[@]+"${HTTP_HEADERS[@]}"}"; do
		curl_parts+=(-H "$h")
	done
	if [[ -n ${HTTP_BODY_FILE:-} ]]; then
		[[ -f $HTTP_BODY_FILE ]] || die "body file not found: $HTTP_BODY_FILE"
		curl_parts+=(-H "Content-Type: application/json" -d "$(cat "$HTTP_BODY_FILE")")
	fi

	local inner=""
	local p
	for p in "${curl_parts[@]}"; do
		inner+=" $(printf '%q' "$p")"
	done
	local shell_cmd="code=\$(${inner}); echo \"\$code\"; cat /tmp/body"

	local pod="pca-v-${RUN_ID}-$(printf '%04x' "$RANDOM")"
	pod="${pod,,}"
	if ((${#pod} > 63)); then
		pod="pca-v-${RANDOM}${RANDOM}"
	fi

	oc delete pod "$pod" -n "$AI_NAMESPACE" --ignore-not-found >/dev/null 2>&1 || true
	local result
	set +e
	result=$(
		oc run "$pod" --rm -i --restart=Never \
			-n "$AI_NAMESPACE" \
			--image="$CURL_IMAGE" \
			--labels="app.kubernetes.io/name=verify-pca,verify-pca.run=${RUN_ID}" \
			--command -- sh -c "$shell_cmd" 2>/dev/null
	)
	local rc=$?
	set -e
	[[ $rc -eq 0 || -n $result ]] || die "oc run curl pod failed for $url (rc=$rc). If OC_USER cannot create pods in $AI_NAMESPACE (Forbidden), drive VIA=opencode instead of curling the AI namespace. Check image pull of $CURL_IMAGE in $AI_NAMESPACE."

	result=$(printf '%s' "$result" | sed -E 's/[[:space:]]*pod "[^"]+" deleted[[:space:]]*$//')

	local status="" body=""
	local line found=0
	while IFS= read -r line; do
		if [[ $found -eq 0 && $line =~ ^[0-9]{3}$ ]]; then
			status="$line"
			found=1
			continue
		fi
		if [[ $found -eq 1 ]]; then
			if [[ -n $body ]]; then
				body+=$'\n'
			fi
			body+="$line"
		fi
	done <<<"$result"

	[[ -n $status ]] || die "could not parse HTTP status from curl output for $url: ${result:0:300}"

	local out="${HTTP_OUT:-$EVIDENCE_DIR/last-body}"
	printf '%s\n' "$body" >"$out"
	printf '%s\n' "$status" >"$EVIDENCE_DIR/last-status"
	printf '%s\n' "$url" >"$EVIDENCE_DIR/last-url"
	printf '%s\n' "$method" >"$EVIDENCE_DIR/last-method"
	echo "STATUS=$status"
	echo "URL=$url"
	echo "BODY_PATH=$out"
	echo "EVIDENCE_DIR=$EVIDENCE_DIR"
	LAST_STATUS="$status"
	LAST_BODY="$body"
	LAST_BODY_PATH="$out"
}

cmd_doctor() {
	need_login
	ensure_evidence
	local ns_ok=false llmis_ready="" llmd_acc="" ai_acc="absent" pvc="" model=""
	local key_present="unset" gw_present="false" workload_ok="false"
	local err="" mode="ai" can_run="false"
	local ide_url="" ide_via="unset" dw_ok="false"
	local access
	access=$(ai_namespace_access)

	if [[ $access == ok ]]; then
		ns_ok=true
		if oc auth can-i create pods -n "$AI_NAMESPACE" >/dev/null 2>&1; then
			can_run="true"
		fi
	elif [[ $access == forbidden ]]; then
		mode="devspace"
	else
		err="namespace $AI_NAMESPACE missing — deploy with .cursor/skills/deploy-existing-openshift, do not invent a second stack"
	fi

	if [[ $ns_ok == true ]]; then
		if oc get llminferenceservice "$LLMIS_NAME" -n "$AI_NAMESPACE" >/dev/null 2>&1; then
			llmis_ready=$(condition_status llminferenceservice "$LLMIS_NAME" Ready || true)
		else
			err="LLMInferenceService/$LLMIS_NAME missing in $AI_NAMESPACE"
		fi
		if oc get gateway "$LLMD_GATEWAY" -n "$AI_NAMESPACE" >/dev/null 2>&1; then
			llmd_acc=$(condition_status gateway "$LLMD_GATEWAY" Accepted || true)
		else
			err="Gateway/$LLMD_GATEWAY missing in $AI_NAMESPACE"
		fi
		if oc get gateway "$AI_GATEWAY" -n "$AI_NAMESPACE" >/dev/null 2>&1; then
			gw_present="true"
			ai_acc=$(condition_status gateway "$AI_GATEWAY" Accepted || true)
		fi
		pvc=$(oc get pvc model-cache -n "$AI_NAMESPACE" -o jsonpath='{.status.phase}' 2>/dev/null || echo missing)
		model=$(model_id)
		local label pods=0
		for label in \
			"app.kubernetes.io/name=${LLMIS_NAME},app.kubernetes.io/component=llminferenceservice-workload" \
			"app.kubernetes.io/name=${LLMIS_NAME}" \
			"kserve.io/component=workload,app.kubernetes.io/name=${LLMIS_NAME}"; do
			pods=$(oc get pods -n "$AI_NAMESPACE" -l "$label" --no-headers 2>/dev/null |
				awk '$3=="Running"{c++} END{print c+0}')
			if [[ ${pods:-0} -ge 1 ]]; then
				workload_ok="true"
				break
			fi
		done
	fi

	local dns
	dns=$(dev_namespace)
	if [[ -n $dns ]]; then
		if oc get dw code-workspace-1 -n "$dns" >/dev/null 2>&1; then
			dw_ok="true"
			ide_url=$(ide_base_url_from_dw "$dns" code-workspace-1)
			ide_via=$(ide_via_from_url "$ide_url")
		fi
		if oc get secret "$APIKEY_SECRET" -n "$dns" >/dev/null 2>&1; then
			local k
			k=$(oc get secret "$APIKEY_SECRET" -n "$dns" -o jsonpath="{.data.${APIKEY_KEY}}" 2>/dev/null || true)
			if [[ -n $k ]]; then
				key_present="true"
			else
				key_present="empty"
			fi
		else
			key_present="missing"
		fi
	fi

	local ok=true
	if [[ $mode == ai ]]; then
		[[ $ns_ok == true ]] || ok=false
		[[ $llmis_ready == True ]] || ok=false
		[[ $llmd_acc == True ]] || ok=false
		[[ $pvc == Bound ]] || ok=false
		[[ $workload_ok == true ]] || ok=false
		if [[ $gw_present == true && $ai_acc != True ]]; then
			ok=false
		fi
	else
		# Demo user: Forbidden on AI_NAMESPACE is not "undeployed".
		# tests/e2e drives OpenCode in <whoami>-devspaces without listing the AI ns.
		if [[ -z $dns ]]; then
			err="OC_USER=$OC_USER cannot see $AI_NAMESPACE (Forbidden) and has no ${OC_USER}-devspaces. Log in as a serving admin or a user that owns a DevSpace. Do not helm-deploy."
			ok=false
		elif [[ $dw_ok != true ]]; then
			err="DevWorkspace code-workspace-1 missing in $dns"
			ok=false
		elif [[ $ide_via == gateway && $key_present != true ]]; then
			err="IDE_VIA=gateway but API_KEY_PRESENT=$key_present in $dns (chat needs secret/$APIKEY_SECRET)"
			ok=false
		fi
	fi
	if [[ -n $err ]]; then
		ok=false
	fi

	{
		echo "OK=$ok"
		echo "MODE=$mode"
		echo "OC_USER=$OC_USER"
		echo "AI_NAMESPACE=$AI_NAMESPACE"
		echo "AI_NAMESPACE_ACCESS=$access"
		echo "AI_NAMESPACE_CAN_RUN_PODS=$can_run"
		echo "LLMIS_NAME=$LLMIS_NAME"
		echo "LLMIS_READY=${llmis_ready:-unknown}"
		echo "LLMD_GATEWAY_ACCEPTED=${llmd_acc:-unknown}"
		echo "AI_GATEWAY_PRESENT=$gw_present"
		echo "AI_GATEWAY_ACCEPTED=$ai_acc"
		echo "PVC_PHASE=${pvc:-unknown}"
		echo "WORKLOAD_POD_RUNNING=$workload_ok"
		echo "MODEL_ID=$model"
		echo "DEV_USER=${DEV_USER:-}"
		echo "DEV_NAMESPACE=${dns:-}"
		echo "IDE_BASE_URL=${ide_url:-}"
		echo "IDE_VIA=$ide_via"
		echo "API_KEY_PRESENT=$key_present"
		echo "RUN_ID=$RUN_ID"
		echo "EVIDENCE_DIR=$EVIDENCE_DIR"
		if [[ $mode == devspace ]]; then
			echo "NOTE=drive VIA=opencode (tests/e2e port-forward). Do not oc run curl pods in $AI_NAMESPACE."
		fi
		if [[ -n $err ]]; then
			echo "ERROR=$err"
		fi
	} | tee "$EVIDENCE_DIR/doctor.txt"

	[[ $ok == true ]]
}

cmd_models() {
	need_login
	ensure_evidence
	local url
	url="$(via_v1)/models"
	if [[ $VIA == gateway ]]; then
		local key
		key=$(apikey)
		HTTP_HEADERS=("Authorization: Bearer ${key}")
	else
		HTTP_HEADERS=()
	fi
	HTTP_OUT="$EVIDENCE_DIR/models-body.json"
	in_cluster_http GET "$url" 60
	[[ $LAST_STATUS == 200 ]] || die "GET /v1/models returned $LAST_STATUS (see $HTTP_OUT)"
	local mid
	mid=$(model_id)
	python3 - "$HTTP_OUT" "$mid" <<'PY'
import json, sys
path, mid = sys.argv[1], sys.argv[2]
body = json.loads(open(path).read() or "{}")
ids = [m.get("id") for m in (body.get("data") or [])]
if mid not in ids and not any(mid in (i or "") for i in ids):
    sys.exit(f"model {mid!r} not in /v1/models: {ids}")
print(f"MODELS={ids}")
print(f"MODEL_ID_OK={mid}")
PY
}

cmd_chat() {
	need_login
	ensure_evidence
	if [[ $VIA == opencode ]]; then
		cmd_opencode_chat
		return
	fi
	if [[ $VIA != llmd && $(ai_namespace_access) == forbidden ]]; then
		log "OC_USER=$OC_USER cannot oc run in $AI_NAMESPACE (Forbidden); VIA=opencode like tests/e2e"
		cmd_opencode_chat
		return
	fi
	local mid prompt max_tokens url
	mid=$(model_id)
	prompt="${PROMPT:-Reply with the single word pong. Token: pca-verify-${RUN_ID}}"
	max_tokens="${MAX_TOKENS:-32}"
	url="$(via_v1)/chat/completions"
	local req="$EVIDENCE_DIR/chat-request.json"
	python3 - "$req" "$mid" "$prompt" "$max_tokens" <<'PY'
import json, sys
path, mid, prompt, max_tokens = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
json.dump(
    {
        "model": mid,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "max_tokens": max_tokens,
    },
    open(path, "w"),
    indent=2,
)
print(path)
PY
	HTTP_HEADERS=()
	if [[ $VIA == gateway ]]; then
		HTTP_HEADERS=("Authorization: Bearer $(apikey)" "X-PCA-User: verify-pca" "X-PCA-DevSpace: $(dev_namespace)")
	fi
	HTTP_BODY_FILE="$req"
	HTTP_OUT="$EVIDENCE_DIR/chat-response.json"
	in_cluster_http POST "$url" 180
	[[ $LAST_STATUS == 200 ]] || die "POST /v1/chat/completions returned $LAST_STATUS (see $HTTP_OUT)"
	python3 - "$HTTP_OUT" <<'PY'
import json, sys
body = json.loads(open(sys.argv[1]).read() or "{}")
choices = body.get("choices") or []
if not choices:
    sys.exit(f"empty choices: {body}")
msg = choices[0].get("message") or {}
content = msg.get("content") or msg.get("reasoning") or ""
if not str(content).strip():
    sys.exit(f"empty assistant message: {body}")
print("ASSISTANT=" + str(content).replace("\n", " ")[:500])
print("FINISH=" + str(choices[0].get("finish_reason") or ""))
PY
}

cmd_http() {
	need_login
	[[ $# -ge 2 ]] || die "http requires METHOD URL"
	local method="$1" url="$2"
	HTTP_HEADERS=()
	if [[ -n ${HTTP_HEADER:-} ]]; then
		HTTP_HEADERS=("$HTTP_HEADER")
	fi
	HTTP_OUT="${HTTP_OUT:-$EVIDENCE_DIR/http-body}"
	HTTP_INSECURE="${HTTP_INSECURE:-1}"
	in_cluster_http "$method" "$url" "${HTTP_TIMEOUT:-60}"
}

cmd_grafana_health() {
	need_login
	ensure_evidence
	local url="http://pca-grafana.${AI_NAMESPACE}.svc.cluster.local:3000/api/health"
	HTTP_HEADERS=()
	HTTP_INSECURE=0
	HTTP_OUT="$EVIDENCE_DIR/grafana-health.json"
	in_cluster_http GET "$url" 30
	[[ $LAST_STATUS == 200 ]] || die "Grafana /api/health returned $LAST_STATUS"
	if oc get route pca-grafana -n "$AI_NAMESPACE" >/dev/null 2>&1; then
		echo "GRAFANA_ROUTE=$(oc get route pca-grafana -n "$AI_NAMESPACE" -o jsonpath='{.spec.host}')"
	fi
}

cmd_devspace_status() {
	need_login
	ensure_evidence
	local ns
	ns=$(dev_namespace)
	[[ -n $ns ]] || die "devspace-status needs DEV_USER or DEV_NAMESPACE (or oc whoami user with <user>-devspaces)"
	local dw="code-workspace-1"
	oc get dw "$dw" -n "$ns" >/dev/null 2>&1 || die "DevWorkspace $dw not found in $ns"
	local phase started route ide_url
	phase=$(oc get dw "$dw" -n "$ns" -o jsonpath='{.status.phase}')
	started=$(oc get dw "$dw" -n "$ns" -o jsonpath='{.spec.started}')
	route=$(oc get route -n "$ns" -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.host}{"\n"}{end}' |
		awk '/opencode-web/ { print $2; exit }')
	ide_url=$(ide_base_url_from_dw "$ns" "$dw")
	local secret_ok=false
	if oc get secret opencode-web-password -n "$ns" >/dev/null 2>&1; then
		secret_ok=true
	fi
	{
		echo "DEV_NAMESPACE=$ns"
		echo "DEVWORKSPACE=$dw"
		echo "PHASE=$phase"
		echo "STARTED=$started"
		echo "OPENCODE_WEB_HOST=${route:-}"
		echo "OPENCODE_WEB_PASSWORD_SECRET=$secret_ok"
		echo "IDE_BASE_URL=${ide_url:-}"
		echo "IDE_VIA=$(ide_via_from_url "$ide_url")"
		echo "NOTE=password is in secret opencode-web-password; do not copy it into evidence"
	} | tee "$EVIDENCE_DIR/devspace-status.txt"
}

# Same as tests/e2e: patch started=true and wait for Running (up to 600s).
ensure_devworkspace_running() {
	local ns="$1" name="$2"
	local phase
	phase=$(oc get dw "$name" -n "$ns" -o jsonpath='{.status.phase}' 2>/dev/null || true)
	if [[ $phase != Running ]]; then
		log "starting DevWorkspace $ns/$name (tests/e2e ensure_devworkspace_started)"
		oc patch dw "$name" -n "$ns" --type=merge -p '{"spec":{"started":true}}' >/dev/null
	fi
	local deadline=$((SECONDS + 600))
	while ((SECONDS < deadline)); do
		phase=$(oc get dw "$name" -n "$ns" -o jsonpath='{.status.phase}')
		if [[ $phase == Running ]]; then
			echo "$phase"
			return 0
		fi
		if [[ $phase == Failed || $phase == Error ]]; then
			die "DevWorkspace $ns/$name entered $phase"
		fi
		sleep 5
	done
	die "DevWorkspace $ns/$name not Running within 600s (last phase=${phase:-unknown})"
}

workspace_pod() {
	local ns="$1" name="$2"
	local wid pod
	wid=$(oc get dw "$name" -n "$ns" -o jsonpath='{.status.devworkspaceId}')
	if [[ -n $wid ]]; then
		pod=$(oc get pods -n "$ns" -l "controller.devfile.io/devworkspace_id=${wid}" \
			--no-headers 2>/dev/null | awk '$3=="Running"{print $1; exit}')
		if [[ -n $pod ]]; then
			echo "$pod"
			return 0
		fi
	fi
	pod=$(oc get pods -n "$ns" --no-headers 2>/dev/null |
		awk '$3=="Running" && $1 ~ /^workspace/{print $1; exit}')
	[[ -n $pod ]] || die "no Running workspace pod in $ns"
	echo "$pod"
}

resolve_opencode_model() {
	local ns="$1" pod="$2" out py
	py='import json,os
model=os.environ.get("VLLM_MODEL_ID") or os.environ.get("OPENAI_MODEL") or ""
path=os.path.expanduser("~/.config/opencode/opencode.json")
try:
    cfg=json.load(open(path,encoding="utf-8"))
    m=cfg.get("model") or ""
    if "/" in m:
        p,mid=m.split("/",1)
        print(p); print(mid); raise SystemExit(0)
except Exception:
    pass
print("vllm"); print(model or "unknown")'
	if out=$(oc exec -n "$ns" "$pod" -c dev-tools -- python3 -c "$py" 2>/dev/null); then
		printf '%s\n' "$out"
		return 0
	fi
	oc exec -n "$ns" "$pod" -- python3 -c "$py"
}

cmd_opencode_chat() {
	need_login
	ensure_evidence
	local ns dw="code-workspace-1"
	ns=$(dev_namespace)
	[[ -n $ns ]] || die "opencode-chat needs DEV_USER (or oc whoami with <user>-devspaces)"
	oc get dw "$dw" -n "$ns" >/dev/null 2>&1 || die "DevWorkspace $dw not found in $ns"
	ensure_devworkspace_running "$ns" "$dw" >/dev/null
	local pod
	pod=$(workspace_pod "$ns" "$dw")
	oc get secret opencode-web-password -n "$ns" >/dev/null 2>&1 ||
		die "secret/opencode-web-password missing in $ns"
	local password
	password=$(oc get secret opencode-web-password -n "$ns" -o jsonpath='{.data.password}' | base64 -d)
	[[ -n $password ]] || die "opencode-web-password is empty"
	local prompt
	prompt="${PROMPT:-Reply with the single word pong. Token: pca-verify-${RUN_ID}}"
	local expect="${EXPECT:-clean}"
	local provider="" model=""
	local ids
	ids=$(resolve_opencode_model "$ns" "$pod" || true)
	provider=$(printf '%s\n' "$ids" | sed -n '1p')
	model=$(printf '%s\n' "$ids" | sed -n '2p')

	local local_port
	local_port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')
	local pf_log="$EVIDENCE_DIR/opencode-port-forward.log"
	oc port-forward -n "$ns" "pod/${pod}" "${local_port}:4096" >"$pf_log" 2>&1 &
	local pf_pid=$!
	trap 'kill '"$pf_pid"' 2>/dev/null || true' EXIT
	local i ready=0
	for i in $(seq 1 50); do
		if python3 -c "import socket; s=socket.create_connection(('127.0.0.1', ${local_port}), 1); s.close()" 2>/dev/null; then
			ready=1
			break
		fi
		if ! kill -0 "$pf_pid" 2>/dev/null; then
			die "port-forward exited early (see $pf_log)"
		fi
		sleep 0.2
	done
	[[ $ready -eq 1 ]] || die "port-forward to $ns/$pod:4096 not ready (see $pf_log)"

	{
		echo "DEV_NAMESPACE=$ns"
		echo "DEVWORKSPACE=$dw"
		echo "POD=$pod"
		echo "VIA=opencode"
		echo "EXPECT=$expect"
		echo "IDE_BASE_URL=$(ide_base_url_from_dw "$ns" "$dw")"
	} >"$EVIDENCE_DIR/opencode-chat-meta.txt"

	OPENCODE_URL="http://127.0.0.1:${local_port}" \
		OPENCODE_PASSWORD="$password" \
		OPENCODE_USER=opencode \
		PROMPT="$prompt" \
		EVIDENCE_DIR="$EVIDENCE_DIR" \
		RUN_ID="$RUN_ID" \
		EXPECT="$expect" \
		PROVIDER_ID="$provider" \
		MODEL_ID="$model" \
		python3 "$SCRIPT_DIR/opencode_chat.py"
	local rc=$?
	kill "$pf_pid" 2>/dev/null || true
	trap - EXIT
	wait "$pf_pid" 2>/dev/null || true
	return "$rc"
}

cmd_cleanup() {
	need_login
	if [[ $(ai_namespace_access) != ok ]]; then
		echo "CLEANED_SELECTOR=skipped"
		echo "NOTE=OC_USER=$OC_USER cannot delete pods in $AI_NAMESPACE"
		echo "EVIDENCE_DIR=$EVIDENCE_DIR"
		echo "EVIDENCE_KEPT=$([[ -d $EVIDENCE_DIR ]] && echo true || echo false)"
		return 0
	fi
	local selector="app.kubernetes.io/name=verify-pca"
	if [[ ${1:-} != --all ]]; then
		selector="${selector},verify-pca.run=${RUN_ID}"
	fi
	log "Deleting pods -n $AI_NAMESPACE -l $selector (evidence kept at $EVIDENCE_DIR)"
	oc delete pods -n "$AI_NAMESPACE" -l "$selector" --ignore-not-found --wait=false >/dev/null
	echo "CLEANED_SELECTOR=$selector"
	echo "EVIDENCE_DIR=$EVIDENCE_DIR"
	echo "EVIDENCE_KEPT=$([[ -d $EVIDENCE_DIR ]] && echo true || echo false)"
}

main() {
	local cmd="${1:-}"
	shift || true
	case "$cmd" in
	doctor) cmd_doctor ;;
	models) cmd_models ;;
	chat) cmd_chat ;;
	http) cmd_http "$@" ;;
	grafana-health) cmd_grafana_health ;;
	devspace-status) cmd_devspace_status ;;
	opencode-chat) cmd_opencode_chat ;;
	cleanup) cmd_cleanup "$@" ;;
	-h | --help | help | "") usage ;;
	*)
		usage
		die "unknown command: $cmd"
		;;
	esac
}

main "$@"
