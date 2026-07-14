{{/*
Langfuse settings live under pca-observability.langfuse (single source of truth).
*/}}
{{- define "pca-ai-serving.langfuseEnabled" -}}
{{- $obs := index .Values "pca-observability" | default dict -}}
{{- if and $obs $obs.langfuse $obs.langfuse.enabled -}}true{{- else -}}false{{- end -}}
{{- end -}}

{{- define "pca-ai-serving.langfuseIoCapture" -}}
{{- $obs := index .Values "pca-observability" | default dict -}}
{{- if and $obs $obs.langfuse $obs.langfuse.ioCapture -}}
{{- $obs.langfuse.ioCapture -}}
{{- else -}}full{{- end -}}
{{- end -}}

{{/*
Fail if deprecated top-level langfuse.enabled is set without the subchart flag.
*/}}
{{- define "pca-ai-serving.langfuse.validate" -}}
{{- $obs := index .Values "pca-observability" | default dict -}}
{{- $subEnabled := and $obs $obs.langfuse $obs.langfuse.enabled -}}
{{- if and .Values.langfuse .Values.langfuse.enabled (not $subEnabled) -}}
{{- fail "langfuse.enabled is deprecated; set pca-observability.langfuse.enabled=true instead" -}}
{{- end -}}
{{- end -}}
