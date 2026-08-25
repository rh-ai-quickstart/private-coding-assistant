{{/*
  llm-d ClusterIP URL (escape hatch only).
*/}}
{{- define "pca-devspaces.llmdBaseUrl" -}}
{{- $ns := .Values.aiServingNamespace | default "ai-serving" -}}
{{- printf "https://llm-d-gateway-data-science-gateway-class.%s.svc.cluster.local/v1" $ns -}}
{{- end -}}

{{- define "pca-devspaces.maas.enabled" -}}
{{- $m := .Values.maas | default dict -}}
{{- if hasKey $m "enabled" -}}
{{- $m.enabled -}}
{{- else -}}
true
{{- end -}}
{{- end -}}

{{- define "pca-devspaces.maas.origin" -}}
{{- $m := .Values.maas | default dict -}}
{{- if $m.hostname -}}
{{- printf "https://%s" $m.hostname -}}
{{- else -}}
{{- $name := $m.gatewayName | default "maas-default-gateway" -}}
{{- $class := $m.gatewayClassName | default "data-science-gateway-class" -}}
{{- $ns := $m.gatewayNamespace | default "openshift-ingress" -}}
{{- printf "https://%s-%s.%s.svc.cluster.local" $name $class $ns -}}
{{- end -}}
{{- end -}}

{{- define "pca-devspaces.maas.baseUrl" -}}
{{- printf "%s/v1" (include "pca-devspaces.maas.origin" .) -}}
{{- end -}}

{{- define "pca-devspaces.maas.tabBaseUrl" -}}
{{- printf "%s/local/v1" (include "pca-devspaces.maas.origin" .) -}}
{{- end -}}

{{/*
  IDE mode: escape hatch to llm-d, otherwise MaaS (default).
*/}}
{{- define "pca-devspaces.ideMode" -}}
{{- $ai := .Values.aiGateway | default dict -}}
{{- if $ai.escapeHatchToLlmd | default false -}}
llmd
{{- else if eq (include "pca-devspaces.maas.enabled" .) "true" -}}
maas
{{- else -}}
llmd
{{- end -}}
{{- end -}}

{{/*
  Default IDE OpenAI-compatible base URL.
*/}}
{{- define "pca-devspaces.aiGateway.baseUrl" -}}
{{- if eq (include "pca-devspaces.ideMode" .) "llmd" -}}
{{- include "pca-devspaces.llmdBaseUrl" . -}}
{{- else -}}
{{- include "pca-devspaces.maas.baseUrl" . -}}
{{- end -}}
{{- end -}}

{{- define "pca-devspaces.tabAutocompleteBaseUrl" -}}
{{- if eq (include "pca-devspaces.ideMode" .) "llmd" -}}
{{- include "pca-devspaces.llmdBaseUrl" . -}}
{{- else -}}
{{- include "pca-devspaces.maas.tabBaseUrl" . -}}
{{- end -}}
{{- end -}}

{{/*
  IDE apiKey for tab autocomplete. Authenticated MaaS /local/v1 when MaaS is on.
  EMPTY when tab talks to llm-d directly (escape hatch).
  Caller: dict "root" $ "ns" $devNamespace
*/}}
{{- define "pca-devspaces.tabAutocompleteApiKey" -}}
{{- if eq (include "pca-devspaces.ideMode" .root) "llmd" -}}
EMPTY
{{- else -}}
{{- include "pca-devspaces.aiGateway.ideApiKey" . -}}
{{- end -}}
{{- end -}}

{{/*
  Whether IDEs must present an API key (Bearer).
*/}}
{{- define "pca-devspaces.aiGateway.requiresApiKey" -}}
{{- if eq (include "pca-devspaces.ideMode" .) "maas" -}}
true
{{- else -}}
false
{{- end -}}
{{- end -}}

{{/*
  API key for a DevSpaces namespace.

  Prefer an existing Secret (survives upgrades / rotation).
  Lookup pca-maas-apikey first, then leftover pca-ai-gw-apikey.
  Otherwise use a deterministic key shared across Secret + ConfigMap templates
  in the same Helm render (lookup cannot see Secrets created in this release).

  Caller: dict "root" $ "ns" $devNamespace
*/}}
{{- define "pca-devspaces.aiGateway.apiKey" -}}
{{- $root := .root -}}
{{- $ns := .ns -}}
{{- $secretName := (($root.Values.aiGateway).apiKeySecretName | default "pca-maas-apikey") -}}
{{- $existing := lookup "v1" "Secret" $ns $secretName -}}
{{- if not (and $existing $existing.data (index $existing.data "api_key")) -}}
{{- $existing = lookup "v1" "Secret" $ns "pca-ai-gw-apikey" -}}
{{- end -}}
{{- if and $existing $existing.data (index $existing.data "api_key") -}}
{{- index $existing.data "api_key" | b64dec -}}
{{- else -}}
{{- $seed := (($root.Values.aiGateway).apiKeySeed | default $root.Release.Name) -}}
{{- printf "%s/%s/pca-ai-gw" $seed $ns | sha256sum | trunc 48 -}}
{{- end -}}
{{- end -}}

{{/*
  IDE apiKey field value: real key when required, else EMPTY (llm-d has auth off).
  Caller: dict "root" $ "ns" $devNamespace
*/}}
{{- define "pca-devspaces.aiGateway.ideApiKey" -}}
{{- if eq (include "pca-devspaces.aiGateway.requiresApiKey" .root) "true" -}}
{{- include "pca-devspaces.aiGateway.apiKey" . -}}
{{- else -}}
EMPTY
{{- end -}}
{{- end -}}

{{/*
  Token budgets — keep aligned with pca-ai-serving tokens.*.
*/}}
{{- define "pca-devspaces.tokens.total" -}}
{{- if and .Values.tokens .Values.tokens.total -}}
{{- .Values.tokens.total -}}
{{- else -}}
32000
{{- end -}}
{{- end -}}

{{- define "pca-devspaces.tokens.output" -}}
{{- if and .Values.tokens .Values.tokens.output -}}
{{- .Values.tokens.output -}}
{{- else -}}
8192
{{- end -}}
{{- end -}}

{{/*
  Model variant switch — must stay in sync with pca-ai-serving.modelVariant
  (same "qwen3.6" default / "qwen3.8" override pattern). Terraform sets both
  via the same model_variant value (see PCA_Deployment_ROSA|ARO/terraform).
*/}}
{{- define "pca-devspaces.modelId" -}}
{{- if eq (.Values.modelVariant | default "qwen3.6") "qwen3.8" -}}
Qwen/Qwen3.8-27B-FP8
{{- else -}}
{{- .Values.modelId -}}
{{- end -}}
{{- end -}}

{{/*
  Compact opencode.json body.
  Caller: dict "root" $ "baseURL" <url or $OPENAI_BASE_URL> "modelId" <id or $VLLM_MODEL_ID>
           optional "schemaKey" (default $schema; postStart uses \$schema so the shell
           does not expand it).
*/}}
{{- define "pca-devspaces.opencodeConfigJson" -}}
{{- $root := .root -}}
{{- $baseURL := .baseURL -}}
{{- $modelId := .modelId -}}
{{- $schemaKey := .schemaKey | default "$schema" -}}
{"{{ $schemaKey }}":"https://opencode.ai/config.json","provider":{"vllm":{"npm":"@ai-sdk/openai-compatible","name":"Private AI Gateway (llm-d)","options":{"baseURL":{{ $baseURL | quote }},"extraBody":{"chat_template_kwargs":{"enable_thinking":false}}},"models":{ {{ $modelId | quote }}:{"name":{{ $modelId | quote }},"limit":{"context":{{ include "pca-devspaces.tokens.total" $root }},"output":{{ include "pca-devspaces.tokens.output" $root }}}}}}},"model":{{ printf "vllm/%s" $modelId | quote }},"permission":"allow","default_agent":"build","agent":{"build":{"prompt":"You write files with the write tool. After creating the requested file, reply with one short sentence and stop. Do not run bash, search, or extra tools.","tools":{"write":true,"edit":true,"read":true,"bash":false,"glob":false,"grep":false,"webfetch":false,"websearch":false,"task":false,"skill":false,"lsp":false,"todowrite":false,"todoread":false,"question":false}}}}
{{- end -}}

{{/*
  postStart: write opencode.json from OPENAI_BASE_URL / VLLM_MODEL_ID.
  Callers: devworkspaces.yaml, dashboard sample. Pass chart root ($ or .).
*/}}
{{- define "pca-devspaces.opencodeWriteConfigScript" -}}
mkdir -p ~/.config/opencode ~/.local/share/opencode
cat > ~/.config/opencode/opencode.json <<EOF
{{ include "pca-devspaces.opencodeConfigJson" (dict "root" . "baseURL" "$OPENAI_BASE_URL" "modelId" "$VLLM_MODEL_ID" "schemaKey" (printf "\\$schema")) }}
EOF
echo "{\"vllm\":{\"type\":\"api\",\"key\":\"$OPENAI_API_KEY\"}}" > ~/.local/share/opencode/auth.json
echo "OpenCode config written"
{{- end -}}

{{/*
  Compact opencode.json for the image BuildConfig (baked model id + base URL).
*/}}
{{- define "pca-devspaces.opencodeJson" -}}
{{- include "pca-devspaces.opencodeConfigJson" (dict "root" . "baseURL" (include "pca-devspaces.aiGateway.baseUrl" .) "modelId" (include "pca-devspaces.modelId" .)) -}}
{{- end -}}
