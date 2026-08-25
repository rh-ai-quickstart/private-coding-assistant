{{/*
KServe InferenceService name for prompt injection (keep short for DNS limits).
*/}}
{{- define "guardrails.promptInjectionServiceName" -}}
{{- .Values.guardrails.detectors.promptInjection.inferenceServiceName | default "pi-detector" -}}
{{- end -}}

{{/*
  TrustyAI / proxy LLM host. Direct Service name, not the old pca-llm-upstream CNAME.
  Semantic Router when global.semanticRouter.enabled, else llm-d HTTP :80 (vLLM is HTTPS :8000
  and TrustyAI cannot verify that workload cert).
*/}}
{{- define "pca-guardrails.llmHost" -}}
{{- $explicit := .Values.guardrails.llmService.host | default "" | toString | trim -}}
{{- if and $explicit (ne $explicit "pca-llm-upstream") -}}
{{- $explicit -}}
{{- else if (((.Values.global).semanticRouter).enabled | default false) -}}
pca-semantic-router
{{- else -}}
{{- .Values.llmdGatewayService | default "llm-d-gateway-data-science-gateway-class" -}}
{{- end -}}
{{- end -}}

{{/*
Build the detectors JSON object that the proxy injects into every request.
Input only: never scan the model reply. Streaming still probes TrustyAI
with this object (max_tokens=0) before llm-d tokens.
  { "input": { "prompt_injection": {}, "regex": {"regex": {...}} },
    "output": {} }
*/}}
{{- define "guardrails.detectorsJson" -}}
{{- $input := dict -}}
{{- $output := dict -}}
{{- if .Values.guardrails.detectors.promptInjection.enabled -}}
  {{- $_ := set $input "prompt_injection" (dict) -}}
{{- end -}}
{{- $pii := .Values.guardrails.detectors.piiRegex | default dict -}}
{{- $secrets := .Values.guardrails.detectors.secretsRegex | default dict -}}
{{- $regexInner := dict -}}
{{- if ($pii.enabled | default false) -}}
  {{- range ($pii.detectors | default list) -}}
    {{- $_ := set $regexInner . (dict) -}}
  {{- end -}}
{{- end -}}
{{- if ($secrets.enabled | default false) -}}
  {{- $secretFile := fromYaml (.Files.Get "files/secret-patterns.yaml") -}}
  {{- range ($secretFile.patterns | default list) -}}
    {{- $_ := set $regexInner . (dict) -}}
  {{- end -}}
  {{- range ($secrets.extraPatterns | default list) -}}
    {{- $_ := set $regexInner . (dict) -}}
  {{- end -}}
{{- end -}}
{{- if $regexInner -}}
  {{- $_ := set $input "regex" (dict "regex" $regexInner) -}}
{{- end -}}
{{- dict "input" $input "output" $output | toJson -}}
{{- end -}}
