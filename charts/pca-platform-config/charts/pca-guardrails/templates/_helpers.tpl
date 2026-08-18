{{/*
KServe InferenceService name for prompt injection (keep short for DNS limits).
*/}}
{{- define "guardrails.promptInjectionServiceName" -}}
{{- .Values.guardrails.detectors.promptInjection.inferenceServiceName | default "pi-detector" -}}
{{- end -}}

{{/*
Build the detectors JSON object that the proxy injects into every request.
The format matches the orchestrator's detection API:
  { "input": { "prompt_injection": {}, "regex": {"regex": {...}} },
    "output": { "regex": {"regex": {...}} } }
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
  {{- if ($secrets.enabled | default false) -}}
    {{- $_ := set $output "regex" (dict "regex" $regexInner) -}}
  {{- end -}}
{{- end -}}
{{- dict "input" $input "output" $output | toJson -}}
{{- end -}}
