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
{{- if or .Values.guardrails.detectors.piiRegex.enabled .Values.guardrails.detectors.secretsRegex.enabled -}}
  {{- $regexInner := dict -}}
  {{- if .Values.guardrails.detectors.piiRegex.enabled -}}
    {{- $_ := set $regexInner "email" (dict) -}}
    {{- $_ := set $regexInner "us-social-security-number" (dict) -}}
    {{- $_ := set $regexInner "credit-card" (dict) -}}
  {{- end -}}
  {{- if .Values.guardrails.detectors.secretsRegex.enabled -}}
    {{- range .Values.guardrails.detectors.secretsRegex.patterns -}}
      {{- $_ := set $regexInner . (dict) -}}
    {{- end -}}
  {{- end -}}
  {{- $_ := set $input "regex" (dict "regex" $regexInner) -}}
  {{- if .Values.guardrails.detectors.secretsRegex.enabled -}}
    {{- $_ := set $output "regex" (dict "regex" $regexInner) -}}
  {{- end -}}
{{- end -}}
{{- dict "input" $input "output" $output | toJson -}}
{{- end -}}
