{{/*
  llm-d ClusterIP URL (escape hatch / direct path).
*/}}
{{- define "pca-devspaces.llmdBaseUrl" -}}
{{- $ns := .Values.aiServingNamespace | default "ai-serving" -}}
{{- printf "https://llm-d-gateway-data-science-gateway-class.%s.svc.cluster.local/v1" $ns -}}
{{- end -}}

{{/*
  Default IDE OpenAI-compatible base URL.

  Priority:
    1. guardrails.enabled → guardrails.endpoint/v1
    2. escapeHatchToLlmd OR aiGateway disabled → llm-d
    3. else → RHCL pca-ai-gateway /v1
*/}}
{{- define "pca-devspaces.aiGateway.baseUrl" -}}
{{- $ai := .Values.aiGateway | default dict -}}
{{- if .Values.guardrails.enabled -}}
{{- printf "%s/v1" .Values.guardrails.endpoint -}}
{{- else if or ($ai.escapeHatchToLlmd | default false) (not ($ai.enabled | default true)) -}}
{{- include "pca-devspaces.llmdBaseUrl" . -}}
{{- else -}}
{{- $ns := .Values.aiServingNamespace | default "ai-serving" -}}
{{- $name := $ai.name | default "pca-ai-gateway" -}}
{{- $class := $ai.gatewayClassName | default "data-science-gateway-class" -}}
{{- printf "https://%s-%s.%s.svc.cluster.local/v1" $name $class $ns -}}
{{- end -}}
{{- end -}}

{{/*
  Whether IDEs must present an RHCL API key (Bearer).
*/}}
{{- define "pca-devspaces.aiGateway.requiresApiKey" -}}
{{- $ai := .Values.aiGateway | default dict -}}
{{- if and ($ai.enabled | default true) (not ($ai.escapeHatchToLlmd | default false)) (not .Values.guardrails.enabled) -}}
true
{{- else -}}
false
{{- end -}}
{{- end -}}

{{/*
  API key for a DevSpaces namespace.

  Prefer an existing Secret (survives upgrades / rotation).
  Otherwise use a deterministic key shared across Secret + ConfigMap templates
  in the same Helm render (lookup cannot see Secrets created in this release).

  Caller: dict "root" $ "ns" $devNamespace
*/}}
{{- define "pca-devspaces.aiGateway.apiKey" -}}
{{- $root := .root -}}
{{- $ns := .ns -}}
{{- $secretName := (($root.Values.aiGateway).apiKeySecretName | default "pca-ai-gw-apikey") -}}
{{- $existing := lookup "v1" "Secret" $ns $secretName -}}
{{- if and $existing $existing.data (index $existing.data "api_key") -}}
{{- index $existing.data "api_key" | b64dec -}}
{{- else -}}
{{- $seed := (($root.Values.aiGateway).apiKeySeed | default $root.Release.Name) -}}
{{- printf "%s/%s/pca-ai-gw" $seed $ns | sha256sum | trunc 48 -}}
{{- end -}}
{{- end -}}

{{/*
  IDE apiKey field value: real RHCL key when required, else EMPTY (llm-d has auth off).
  Caller: dict "root" $ "ns" $devNamespace
*/}}
{{- define "pca-devspaces.aiGateway.ideApiKey" -}}
{{- if eq (include "pca-devspaces.aiGateway.requiresApiKey" .root) "true" -}}
{{- include "pca-devspaces.aiGateway.apiKey" . -}}
{{- else -}}
EMPTY
{{- end -}}
{{- end -}}
