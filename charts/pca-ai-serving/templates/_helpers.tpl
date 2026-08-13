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

{{/*
Token budgets: tokens.total / tokens.output.
vllm.maxModelLen remains a deprecated override for --max-model-len.
*/}}
{{- define "pca-ai-serving.tokens.total" -}}
{{- if and .Values.tokens .Values.tokens.total -}}
{{- .Values.tokens.total -}}
{{- else if .Values.vllm.maxModelLen -}}
{{- .Values.vllm.maxModelLen -}}
{{- else -}}
32000
{{- end -}}
{{- end -}}

{{- define "pca-ai-serving.tokens.output" -}}
{{- if and .Values.tokens .Values.tokens.output -}}
{{- .Values.tokens.output -}}
{{- else -}}
8192
{{- end -}}
{{- end -}}

{{/*
HF_HUB_OFFLINE — always 1 for LLMIS local-path load (storage-initializer
populates the PVC before vLLM starts; no HF Hub access needed at runtime).
*/}}
{{- define "pca-ai-serving.hfHubOffline" -}}
1
{{- end -}}
