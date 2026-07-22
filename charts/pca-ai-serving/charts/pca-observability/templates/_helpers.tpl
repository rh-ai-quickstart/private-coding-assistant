{{/*
Namespace for observability resources.
*/}}
{{- define "pca-observability.namespace" -}}
{{- if .Values.namespace -}}
{{- .Values.namespace -}}
{{- else -}}
{{- .Release.Namespace -}}
{{- end -}}
{{- end -}}

{{/*
Thanos querier URL for Grafana Prometheus datasource.
*/}}
{{- define "pca-observability.thanosUrl" -}}
{{- if .Values.prometheus.thanosUrl -}}
{{- .Values.prometheus.thanosUrl -}}
{{- else if eq .Values.prometheus.accessMode "namespace" -}}
https://thanos-querier.openshift-monitoring.svc.cluster.local:9092
{{- else -}}
https://thanos-querier.openshift-monitoring.svc.cluster.local:9091
{{- end -}}
{{- end -}}

{{/*
OTel Collector service URL (gRPC OTLP).
*/}}
{{- define "pca-observability.otelEndpoint" -}}
http://pca-otel-collector.{{ include "pca-observability.namespace" . }}.svc.cluster.local:4317
{{- end -}}

{{/*
Langfuse web service URL (in-cluster).
*/}}
{{- define "pca-observability.langfuseUrl" -}}
http://{{ .Release.Name }}-langfuse-web.{{ include "pca-observability.namespace" . }}.svc.cluster.local:3000
{{- end -}}
