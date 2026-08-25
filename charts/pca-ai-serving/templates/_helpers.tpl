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

{{/*
  llm-d Gateway Service name: {gatewayName}-{gatewayClassName}.
  HTTPRoute backends and TrustyAI llmService.host must use this same name.
*/}}
{{- define "pca-ai-serving.llmdGatewayService" -}}
{{- printf "%s-%s" (.Values.gatewayName | default "llm-d-gateway") (.Values.aiGateway.gatewayClassName | default "data-science-gateway-class") -}}
{{- end -}}

{{/*
  Model variant switch — only one model is deployed at a time. "qwen3.6" (the
  default) is a pure passthrough of the model.* / vllm.* values below, so
  existing deployments that never set model.variant are unaffected. Setting
  model.variant=qwen3.8 overrides the six fields that differ for
  Qwen/Qwen3.8-27B-FP8 (validated config — see docs/qwen3.8-model-migration.md).
  Deploying both variants concurrently behind one AI Gateway is unsupported:
  it triggers a Kuadrant EnvoyFilter-ordering bug that OOM-crashes llm-d-gateway.
*/}}
{{- define "pca-ai-serving.modelVariant" -}}
{{- .Values.model.variant | default "qwen3.6" -}}
{{- end -}}

{{- define "pca-ai-serving.model.id" -}}
{{- if eq (include "pca-ai-serving.modelVariant" .) "qwen3.8" -}}
Qwen/Qwen3.8-27B-FP8
{{- else -}}
{{- .Values.model.id -}}
{{- end -}}
{{- end -}}

{{- define "pca-ai-serving.model.name" -}}
{{- if eq (include "pca-ai-serving.modelVariant" .) "qwen3.8" -}}
qwen3-8-coder
{{- else -}}
{{- .Values.model.name -}}
{{- end -}}
{{- end -}}

{{- define "pca-ai-serving.model.poolName" -}}
{{- if eq (include "pca-ai-serving.modelVariant" .) "qwen3.8" -}}
qwen3-8-coder-inference-pool
{{- else -}}
{{- .Values.model.poolName -}}
{{- end -}}
{{- end -}}

{{- define "pca-ai-serving.vllm.image" -}}
{{- if eq (include "pca-ai-serving.modelVariant" .) "qwen3.8" -}}
vllm/vllm-openai:v0.27.0
{{- else -}}
{{- .Values.vllm.image -}}
{{- end -}}
{{- end -}}

{{- define "pca-ai-serving.vllm.toolCallParser" -}}
{{- if eq (include "pca-ai-serving.modelVariant" .) "qwen3.8" -}}
qwen3_coder
{{- else -}}
{{- .Values.vllm.toolCallParser -}}
{{- end -}}
{{- end -}}

{{- define "pca-ai-serving.vllm.gpuMemoryUtilization" -}}
{{- if eq (include "pca-ai-serving.modelVariant" .) "qwen3.8" -}}
0.92
{{- else -}}
{{- .Values.vllm.gpuMemoryUtilization -}}
{{- end -}}
{{- end -}}

{{/*
  Qwen3.6's extraArgs are Mamba/MoE-specific (max-num-batched-tokens sized to
  Mamba block_size, cudagraph capture tuned to its activation footprint) and
  don't apply to Qwen3.8's dense architecture — see docs/qwen3.8-model-migration.md.
  Returns a JSON array string; consume with `fromJsonArray`.
*/}}
{{- define "pca-ai-serving.vllm.extraArgs" -}}
{{- if eq (include "pca-ai-serving.modelVariant" .) "qwen3.8" -}}
{{- list "--max-num-seqs=128" | toJson -}}
{{- else -}}
{{- .Values.vllm.extraArgs | toJson -}}
{{- end -}}
{{- end -}}

{{- define "pca-ai-serving.maasGatewayService" -}}
{{- $m := .Values.maas | default dict -}}
{{- $name := $m.gatewayName | default "maas-default-gateway" -}}
{{- $class := $m.gatewayClassName | default (.Values.aiGateway.gatewayClassName | default "data-science-gateway-class") -}}
{{- $ns := $m.gatewayNamespace | default "openshift-ingress" -}}
{{- printf "%s-%s.%s.svc.cluster.local" $name $class $ns -}}
{{- end -}}

{{/*
  Public MaaS vhost. When maas.hostname is set, HTTPRoute hostnames, AuthConfig
  hosts, and EnvoyFilter SNI/vhost all use this string. When empty (existing
  OpenShift default), HTTPRoute omits hostnames and EnvoyFilter matches Istio
  catch-all *:443. Do not fall back to maasGatewayService (Host / SNI mismatch).
*/}}
{{- define "pca-ai-serving.maasPublicHostname" -}}
{{- $m := .Values.maas | default dict -}}
{{- $m.hostname | default "" | toString | trim -}}
{{- end -}}

{{- define "pca-ai-serving.llmUpstreamHost" -}}
{{- if .Values.semanticRouter.enabled -}}
pca-semantic-router
{{- else -}}
{{- include "pca-ai-serving.llmdGatewayService" . -}}
{{- end -}}
{{- end -}}

{{/*
  MaaS HTTPRoute chat backend: guardrails → semantic-router → llm-d :80.
*/}}
{{- define "pca-ai-serving.maasChatBackend.name" -}}
{{- if .Values.guardrails.enabled -}}
guardrails-proxy
{{- else if .Values.semanticRouter.enabled -}}
pca-semantic-router
{{- else -}}
{{- include "pca-ai-serving.llmdGatewayService" . -}}
{{- end -}}
{{- end -}}

{{- define "pca-ai-serving.maasChatBackend.port" -}}
{{- if .Values.guardrails.enabled -}}
8080
{{- else -}}
80
{{- end -}}
{{- end -}}
