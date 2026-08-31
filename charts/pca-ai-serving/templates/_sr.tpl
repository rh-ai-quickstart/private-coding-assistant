{{/*
Semantic Router helpers. Operator extras live on .Values.semanticRouter.
Local Qwen is always injected from model.id; never listed in models[].
*/}}

{{- define "pca-ai-serving.sr.ns" -}}
{{- .Values.namespace | default "ai-serving" -}}
{{- end -}}

{{- define "pca-ai-serving.sr.localModelId" -}}
{{- $served := (.Values.model.servedName | default "" | toString | trim) -}}
{{- if $served -}}
{{- $served -}}
{{- else -}}
{{- include "pca-ai-serving.model.id" . -}}
{{- end -}}
{{- end -}}

{{- define "pca-ai-serving.sr.llmdHost" -}}
{{- printf "%s.%s.svc.cluster.local" (include "pca-ai-serving.llmdGatewayService" .) (include "pca-ai-serving.sr.ns" .) -}}
{{- end -}}

{{/* Returns extra models as a JSON array string; consume with fromJsonArray. */}}
{{- define "pca-ai-serving.sr.extras" -}}
{{- $sr := .Values.semanticRouter | default dict -}}
{{- $fromJson := $sr.modelsJson | default "" -}}
{{- if kindIs "slice" $fromJson -}}
{{- $fromJson | toJson -}}
{{- else if and (kindIs "string" $fromJson) ($fromJson | toString | trim) (ne ($fromJson | toString | trim) "[]") -}}
{{- fromJsonArray ($fromJson | toString) | toJson -}}
{{- else -}}
{{- $sr.models | default list | toJson -}}
{{- end -}}
{{- end -}}

{{- define "pca-ai-serving.sr.apiKeys" -}}
{{- $sr := .Values.semanticRouter | default dict -}}
{{- $raw := $sr.apiKeysJson | default dict -}}
{{- if kindIs "map" $raw -}}
{{- $raw | toJson -}}
{{- else -}}
{{- $s := $raw | toString | trim -}}
{{- if and $s (ne $s "{}") -}}
{{- mustFromJson $s | toJson -}}
{{- else -}}
{{- dict | toJson -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "pca-ai-serving.sr.strengthRank" -}}
{{- $s := . | toString | lower | trim -}}
{{- if eq $s "weak" -}}0
{{- else if eq $s "strong" -}}1
{{- else if regexMatch "^[0-9]+$" $s -}}{{ $s }}
{{- else -}}1
{{- end -}}
{{- end -}}

{{- define "pca-ai-serving.sr.envKey" -}}
{{- printf "SR_KEY_%s" (regexReplaceAll "[^A-Za-z0-9]" (. | toString) "_") -}}
{{- end -}}

{{- define "pca-ai-serving.sr.secretName" -}}
{{- printf "pca-sr-%s" . -}}
{{- end -}}

{{- define "pca-ai-serving.sr.parseEndpoint" -}}
{{- $raw := . | toString | trim -}}
{{- $tls := false -}}
{{- $rest := $raw -}}
{{- if hasPrefix "https://" $raw -}}
{{- $tls = true -}}
{{- $rest = trimPrefix "https://" $raw -}}
{{- else if hasPrefix "http://" $raw -}}
{{- $rest = trimPrefix "http://" $raw -}}
{{- end -}}
{{- $slash := splitList "/" $rest -}}
{{- $hostport := index $slash 0 -}}
{{- $path := "" -}}
{{- if gt (len $slash) 1 -}}
{{- $path = printf "/%s" (join "/" (rest $slash) | trimSuffix "/") -}}
{{- if eq $path "/" -}}{{- $path = "" -}}{{- end -}}
{{- end -}}
{{- $host := $hostport -}}
{{- $port := 80 -}}
{{- if $tls }}{{- $port = 443 -}}{{- end -}}
{{- if contains ":" $hostport -}}
{{- $host = (splitList ":" $hostport) | first -}}
{{- $port = (splitList ":" $hostport) | last | int -}}
{{- end -}}
{{- dict "host" $host "port" $port "tls" $tls "pathPrefix" $path | toJson -}}
{{- end -}}

{{- define "pca-ai-serving.sr.embeddingModel" -}}
{{- $sr := .Values.semanticRouter | default dict -}}
{{- $emb := $sr.embedding | default dict -}}
{{- $emb.model | default "sentence-transformers/all-MiniLM-L6-v2" -}}
{{- end -}}

{{- define "pca-ai-serving.sr.codeKeywords" -}}
{{- $sr := .Values.semanticRouter | default dict -}}
{{- $kw := $sr.keywords | default dict -}}
{{- $code := $kw.code | default (list "implement" "refactor" "debug" "function" "class" "python" "javascript" "typescript" "golang" "code") -}}
{{- $code | toJson -}}
{{- end -}}

{{- define "pca-ai-serving.sr.strongestExtra" -}}
{{- $extras := include "pca-ai-serving.sr.extras" . | fromJsonArray -}}
{{- $best := dict -}}
{{- $bestRank := -1 -}}
{{- range $m := $extras -}}
{{- $rank := include "pca-ai-serving.sr.strengthRank" ($m.strength | default "strong") | int -}}
{{- if gt $rank $bestRank -}}
{{- $bestRank = $rank -}}
{{- $best = $m -}}
{{- end -}}
{{- end -}}
{{- $best | toJson -}}
{{- end -}}

{{- define "pca-ai-serving.sr.validateExtras" -}}
{{- $extras := include "pca-ai-serving.sr.extras" . | fromJsonArray -}}
{{- $keys := include "pca-ai-serving.sr.apiKeys" . | fromJson -}}
{{- range $m := $extras -}}
{{- $name := required "semanticRouter extra needs name" $m.name -}}
{{- if eq $name "local" -}}
{{- fail "semanticRouter extras must not list local Qwen; Helm injects it from model.id" -}}
{{- end -}}
{{- if not (regexMatch "^[a-z0-9]([-a-z0-9]*[a-z0-9])?$" $name) -}}
{{- fail (printf "semanticRouter extra name %q must be a DNS-1123 label" $name) -}}
{{- end -}}
{{- if not $m.endpoint -}}
{{- fail (printf "semanticRouter extra %q needs endpoint" $name) -}}
{{- end -}}
{{- if not $m.modelId -}}
{{- fail (printf "semanticRouter extra %q needs modelId" $name) -}}
{{- end -}}
{{- $existing := $m.apiKeySecret | default "" | toString | trim -}}
{{- $injected := index $keys $name | default "" | toString | trim -}}
{{- if and (not $existing) (not $injected) -}}
{{- fail (printf "semanticRouter extra %q needs semanticRouter.apiKeysJson[%s] or apiKeySecret" $name $name) -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "pca-ai-serving.sr.extProcPerRouteDisabled" -}}
typed_per_filter_config:
  envoy.filters.http.ext_proc:
    "@type": type.googleapis.com/envoy.extensions.filters.http.ext_proc.v3.ExtProcPerRoute
    disabled: true
{{- end -}}

{{- define "pca-ai-serving.sr.envoyYaml" -}}
{{- $llmdHost := include "pca-ai-serving.sr.llmdHost" . -}}
{{- $extras := include "pca-ai-serving.sr.extras" . | fromJsonArray -}}
admin:
  address:
    socket_address:
      address: 127.0.0.1
      port_value: 9901
static_resources:
  listeners:
    - name: listener_http
      address:
        socket_address:
          address: 0.0.0.0
          port_value: 8800
      filter_chains:
        - filters:
            - name: envoy.filters.network.http_connection_manager
              typed_config:
                "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
                stat_prefix: pca_semantic_router
                codec_type: AUTO
                route_config:
                  name: local_route
                  virtual_hosts:
                    - name: local_service
                      domains: ["*"]
                      routes:
                        - match:
                            path: "/healthz"
                          direct_response:
                            status: 200
                            body:
                              inline_string: "ok"
                          {{- include "pca-ai-serving.sr.extProcPerRouteDisabled" . | nindent 26 }}
                        - match:
                            path: "/readyz"
                          direct_response:
                            status: 200
                            body:
                              inline_string: "ok"
                          {{- include "pca-ai-serving.sr.extProcPerRouteDisabled" . | nindent 26 }}
                        - match:
                            prefix: "/tokenize"
                          route:
                            cluster: llmd_cluster
                            timeout: 300s
                            host_rewrite_literal: {{ $llmdHost | quote }}
                          {{- include "pca-ai-serving.sr.extProcPerRouteDisabled" . | nindent 26 }}
                        - match:
                            prefix: "/detokenize"
                          route:
                            cluster: llmd_cluster
                            timeout: 300s
                            host_rewrite_literal: {{ $llmdHost | quote }}
                          {{- include "pca-ai-serving.sr.extProcPerRouteDisabled" . | nindent 26 }}
{{- range $m := $extras }}
{{- $ep := include "pca-ai-serving.sr.parseEndpoint" $m.endpoint | fromJson }}
                        - match:
                            prefix: "/v1/chat/completions"
                            headers:
                              - name: x-selected-model
                                string_match:
                                  exact: {{ $m.name | quote }}
                          route:
                            cluster: {{ printf "%s_cluster" $m.name }}
                            timeout: 1200s
                            host_rewrite_literal: {{ $ep.host | quote }}
{{- if and $ep.pathPrefix (ne $ep.pathPrefix "/v1") }}
                            regex_rewrite:
                              pattern:
                                google_re2: {}
                                regex: "^/v1(.*)$"
                              substitution: {{ printf "%s\\1" $ep.pathPrefix | quote }}
{{- end }}
{{- end }}
                        - match:
                            prefix: "/v1/chat/completions"
                            headers:
                              - name: x-selected-model
                                string_match:
                                  exact: local
                          route:
                            cluster: llmd_cluster
                            timeout: 1200s
                            host_rewrite_literal: {{ $llmdHost | quote }}
                        - match:
                            prefix: "/v1/chat/completions"
                          route:
                            cluster: llmd_cluster
                            timeout: 1200s
                            host_rewrite_literal: {{ $llmdHost | quote }}
                        - match:
                            prefix: "/"
                          route:
                            cluster: llmd_cluster
                            timeout: 300s
                            host_rewrite_literal: {{ $llmdHost | quote }}
                          {{- include "pca-ai-serving.sr.extProcPerRouteDisabled" . | nindent 26 }}
                http_filters:
                  - name: envoy.filters.http.ext_proc
                    typed_config:
                      "@type": type.googleapis.com/envoy.extensions.filters.http.ext_proc.v3.ExternalProcessor
                      grpc_service:
                        envoy_grpc:
                          cluster_name: extproc_service
                      allow_mode_override: true
                      disable_clear_route_cache: false
                      processing_mode:
                        request_header_mode: "SEND"
                        response_header_mode: "SEND"
                        request_body_mode: "BUFFERED"
                        response_body_mode: "BUFFERED"
                        request_trailer_mode: "SKIP"
                        response_trailer_mode: "SKIP"
                      failure_mode_allow: true
                      message_timeout: 300s
                  - name: envoy.filters.http.router
                    typed_config:
                      "@type": type.googleapis.com/envoy.extensions.filters.http.router.v3.Router
                      suppress_envoy_headers: true
  clusters:
    - name: extproc_service
      connect_timeout: 300s
      type: STATIC
      lb_policy: ROUND_ROBIN
      typed_extension_protocol_options:
        envoy.extensions.upstreams.http.v3.HttpProtocolOptions:
          "@type": type.googleapis.com/envoy.extensions.upstreams.http.v3.HttpProtocolOptions
          explicit_http_config:
            http2_protocol_options:
              connection_keepalive:
                interval: 300s
                timeout: 300s
      load_assignment:
        cluster_name: extproc_service
        endpoints:
          - lb_endpoints:
              - endpoint:
                  address:
                    socket_address:
                      address: 127.0.0.1
                      port_value: 50051
    - name: llmd_cluster
      connect_timeout: 300s
      type: LOGICAL_DNS
      dns_lookup_family: V4_ONLY
      lb_policy: ROUND_ROBIN
      load_assignment:
        cluster_name: llmd_cluster
        endpoints:
          - lb_endpoints:
              - endpoint:
                  address:
                    socket_address:
                      address: {{ $llmdHost }}
                      port_value: 80
{{- range $m := $extras }}
{{- $ep := include "pca-ai-serving.sr.parseEndpoint" $m.endpoint | fromJson }}
    - name: {{ printf "%s_cluster" $m.name }}
      connect_timeout: 1200s
      type: LOGICAL_DNS
      dns_lookup_family: V4_ONLY
      lb_policy: ROUND_ROBIN
      load_assignment:
        cluster_name: {{ printf "%s_cluster" $m.name }}
        endpoints:
          - lb_endpoints:
              - endpoint:
                  address:
                    socket_address:
                      address: {{ $ep.host }}
                      port_value: {{ $ep.port }}
{{- if $ep.tls }}
      transport_socket:
        name: envoy.transport_sockets.tls
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.UpstreamTlsContext
          sni: {{ $ep.host }}
          common_tls_context:
            tls_params:
              tls_minimum_protocol_version: TLSv1_2
              tls_maximum_protocol_version: TLSv1_3
{{- end }}
{{- end }}
{{- end -}}
