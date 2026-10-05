# Inference traffic flow — deployment view

Content brief for [architecture-traffic-flow.svg](architecture-traffic-flow.svg). The diagram shows the application's inference topology with guardrails, Semantic Router, EPP, and observability drawn as connected components, without availability or enabled labels.

## Scenario

Depict MaaS / RHCL, input guardrails, Semantic Router, EPP, Prometheus / Grafana, OTel Collector, and Langfuse with full prompt/completion capture. Include external model APIs as an optional destination to the left of the cluster. Show an illustrative scale-out topology with separate vLLM replica pods, each containing an NVIDIA GPU tile and PVC storage strip. Each request follows its selected backend and replica path.

The EPP path is an **illustrative custom integration**. The supplied catch-all HTTPRoute still targets the workload Service; setting `epp.enabled=true` alone does not route requests through EPP. The diagram assumes the gateway route and upstream protocol integration have also been configured. It does not represent an infrastructure or code change made by updating this image.

The replica pods and their storage are also illustrative. The supplied LLMInferenceService creates one replica mounting the `model-cache` PVC; it does not provision separate PVCs per replica. The image depicts the requested scale-out layout rather than the supplied replica count or storage provisioning.

The main flow covers inference and its observability. The right-side capabilities panel lists only the OpenShift AI capabilities used by the project's inference stack. MCP tools, provisioning, downloads, and benchmark jobs remain outside its scope.

## Visual style

Preserve the old diagram's pale grid background, red OpenShift boundary header, rounded white cards, colored gradient headings, subtle shadows, compact sans-serif text, and numbered flow. Keep Semantic Router in the main vertical flow as step 4, directly below guardrails. Place the external model card outside the cluster boundary on the left. Arrange three panels on the right, from top to bottom: **KEY ARCHITECTURE PROPERTIES**, **OPENSHIFT AI CAPABILITIES**, and **OBSERVABILITY**. Remove the separate Routing Decisions panel and bottom request-flow legend.

Use a **1430 × 1336** canvas with larger text and generous vertical spacing. Increase card heights and line spacing together, preserving the existing column widths, rounded corners, and unstretched letter shapes.

Use deep blue for the developer workspace, purple for MaaS / RHCL, amber for guardrails, teal for Semantic Router and its optional external-model destination, blue for the combined llm-d / EPP stage, and green for vLLM replicas. Keep assistant tiles teal, GPU tiles dark green, and PVC strips orange. Within step 5, retain a purple gateway tile and blue Envoy / EPP tile. Use darker gradients for readable white heading text; keep white card bodies and pale component backgrounds.

Match each workflow's step badge, border, labels, and outgoing request arrows to its stage color. Keep solid local arrows, the dashed optional external branch, and dotted slate telemetry. Preserve the existing red OpenShift AI panel and slate properties / observability panels. Omit availability, enabled badges, disabled-feature chat bypasses, and cloud-default status labels.

## Title and boundary

- Title: **Inference Traffic Flow**
- Subtitle: **Private AI Code Assistant on Red Hat OpenShift**
- Cluster header: **OPENSHIFT CLUSTER**
- Boundary note: **Private AI Code Assistant · Inference traffic and observability**

Place all local components inside the boundary. External model APIs sit outside it. Explain the custom EPP and scale-out topology in the properties panel and retain **Custom EPP integration shown for this scenario** in step 5.

## Numbered request stages

### 1. Developer workspace

Heading: **DEVELOPER WORKSPACE — OpenShift Dev Spaces**

Editor: **VS Code for the Web (che-code)**

Supporting line: **Per-developer namespace · Workspace storage · Terminal**

Assistant tiles:

- **OpenCode — Default** / **Coding agent · CLI + Web**
- **Continue** / **Chat + Tab autocomplete**
- **Cline** / **Coding agent · Tool calling**
- **Roo Code** / **Code · Architect · Debug**

OpenCode remains the default assistant choice. Continue, Cline, and Roo Code are supplied together in the alternative workspace type. Both types use che-code.

Use exactly one outgoing connection from step 1 to step 2: **OpenAI-compatible API · HTTPS** / **POST /v1/chat/completions · Bearer API key**. Omit the separate Continue autocomplete arrow.

### 2. MaaS / RHCL gateway

Heading: **MaaS / RHCL GATEWAY**

Resource: **maas-default-gateway**

Supporting lines:

- **RHCL / Kuadrant · API keys · Token-limit policy**
- **HTTPS termination · HTTPRoute · openshift-ingress**

RHCL / Kuadrant policies attach to this gateway; they are not another serial proxy hop. Keys are per developer namespace, and the token-limit policy is configured on the PCA route.

Step 2 has one outgoing request arrow, to step 3. Omit the direct MaaS-to-llm-d bypass arrow; keep its explanation in the right-side properties panel.

### 3. Guardrails

Heading: **GUARDRAILS — Input checks**

Components: **guardrails-proxy** ↔ **TrustyAI orchestrator + Detectors**

Detector labels: **Prompt injection · PII · Secrets**

Supporting lines: **Checks input before generation** / **Input only · Probe before SSE streaming**

Blocked branch: **Blocked → Assistant**

Keep TrustyAI inspection inside this group. Streaming requests use an input probe before generation; non-streaming requests use the orchestrator's completion endpoint. Enabling guardrails does not add output checks to the currently generated detector configuration. Blocked input stops before model generation.

### 4. Semantic Router

Heading: **SEMANTIC ROUTER**

Resource: **pca-semantic-router**

Main-card labels: **Local model or external model APIs** / **Selects a backend for each chat request**

Omit the separate Routing Decisions panel and its keyword / complexity routing details. The main Semantic Router card retains the backend-selection labels above.

Place Semantic Router in the main column directly below guardrails, with the step 4 marker on the same left margin as the other main stages. Use one connection from the bottom of the card to a junction. Split that connection into a solid downward arrow to step 5 and a dashed arrow left across the cluster boundary to the external model card, labeled **Optional**. Do not draw a separate arrow from the side of Semantic Router or show a guardrails-off or Semantic-Router-off chat path.

### 5. llm-d inference routing — Gateway + EPP

Heading: **llm-d INFERENCE ROUTING — Gateway + EPP**

Use one card with two internal components:

- **llm-d-gateway** / **Gateway API · HTTPRoute**
- **Envoy + llm-d-epp** / **gRPC endpoint selection**

Connect the gateway to the Envoy / EPP component inside this card. Retain a single step 5 marker on the main flow's left margin; remove the separate EPP card and its step marker.

Scoring chips:

- **Prefix-cache affinity × 3**
- **Queue depth × 2**

Outcome: **InferencePool · Selected local vLLM endpoint**

Supporting note: **Custom EPP integration shown for this scenario**

Draw two outgoing arrows from the bottom of the combined routing card, one to each vLLM replica pod. Place a **SCALE-OUT** chip between the arrows. The arrows represent alternative replica destinations for each request, selected by EPP and forwarded by Envoy.

Show EPP in the local request path. Envoy forwards inference requests and calls EPP for endpoint selection; model tokens do not stream through the EPP scheduler itself. These scorer weights match the configured EPP resources. Omit the old KV-cache-headroom scorer and 0.4 / 0.3 / 0.3 weights.

The local model branch reaches llm-d through its internal HTTP listener. Label HTTPS on the workspace-to-MaaS connection without claiming end-to-end TLS.

### 6. Local model serving

Use two side-by-side model replica cards, matching the GPU tile and storage-strip style of the old GitHub diagram:

- **MODEL REPLICA 1 — vLLM**
- **MODEL REPLICA N — vLLM**

Each card depicts a separate pod with **NVIDIA GPU** / **CUDA inference**, **OpenAI-compatible API**, **Prefix caching**, and **Tool-call parsing** inside. Each has its own visible **Persistent Model Cache (PVC)** strip. Retain one step 6 marker for the replica group.

The two cards depict the requested illustrative scale-out topology, not additional replicas or PVCs created by this documentation change. Prefix caching is independent of EPP.

## External model card

Place outside the OpenShift boundary on the left, alongside step 4:

- Heading: **EXTERNAL MODEL API**
- Labels: **OpenAI-compatible** / **Provider credentials** / **Configured + Selected**

A dashed arrow from the junction below Semantic Router points left to this card and is labeled **Optional**. It represents selecting a configured external backend for that request. External requests bypass the local llm-d / EPP / vLLM branch.

## Continue autocomplete

Describe Continue autocomplete in the right-side properties panel, without drawing separate request arrows in the main flow. Its actual path is:

**Continue → MaaS /local/v1 → Rewrite to /v1 → llm-d → EPP-integrated local serving → vLLM**

Image note: **Continue tab: /local/v1 skips guardrails and Semantic Router.**

This bypass remains correct even when guardrails and Semantic Router are enabled. OpenCode has one configured `/v1` URL; its chat-completion requests follow the full chat path. Other `/v1` requests go directly to llm-d, and `/v1/models` remains public.

## Supporting panels

### Key architecture properties — top right

Use a slate gradient heading and five compact numbered properties:

1. **Explicit inference data boundary** — Local inference and telemetry stay inside OpenShift. External model selection creates an optional egress path.
2. **Workspace separation, shared GPU serving** — Per-developer namespaces, RBAC, storage, and API keys. Developers share the local model service and GPU capacity.
3. **Request-aware API governance** — MaaS / RHCL applies API-key and token-limit policies. Chat input is checked; Continue uses authenticated `/local/v1`.
4. **Separate model policy and replica scheduling** — Semantic Router chooses the backend; EPP picks a local replica. Cache affinity and queue depth guide custom EPP routing.
5. **Declarative serving, persistent model weights** — Helm defines platform resources; KServe reconciles model serving. Model weights live on a retained PVC, outside the pod lifecycle.

These properties explain data residency, developer separation with shared GPU capacity, request-class policy, two-stage routing, and resource / storage lifecycles. Namespace separation describes the project's workspace and RBAC arrangement; it does not claim dedicated GPUs, network-policy isolation, or per-developer GPU quotas. The external branch is a configured routing choice, not proof that all other cluster egress is blocked. Continue's local path skips input guardrails and Semantic Router while retaining API-key authentication. Model/backend policy and local endpoint scheduling are separate decisions in the illustrated custom EPP topology. The supplied chart still has one local replica and a direct workload-Service route. The model-cache PVC has a Helm keep policy and is reused independently of pod replacement; this persistence claim covers model weights, not in-memory prefix or KV cache.

### OpenShift AI capabilities — middle right

Use a red gradient heading and a compact two-by-two grid of individual rounded sub-rectangles. Subtitle: **OpenShift AI capabilities used by PCA**. Keep this panel informational, with no incoming, outgoing, or internal arrows.

Include only these project-used capabilities:

- **KServe Model Serving** / **LLMInferenceService · Model lifecycle**
- **Models as a Service** / **Model refs · Subscriptions · API access**
- **TrustyAI Guardrails** / **Orchestrator · Input detectors**
- **GPU Hardware Profiles** / **CPU · Memory · NVIDIA GPU**

Omit AI Dashboard, Model Registry, AI Pipelines, AI Workbenches, NVIDIA NIM, Workload Variant Autoscaler, generic Platform Monitoring, and Trusted CA Bundle tiles. Enabling or managing a platform component is insufficient to claim that the project uses its workflows. The GPU HardwareProfile is an actual resource supplied by the AI-serving chart; KServe, MaaS, and TrustyAI have project workloads or policy resources.

Remove the dotted **Reconciles** link and its label. Helm supplies gateways, PCA policies, EPP, and observability; one LLMInferenceService does not create all surrounding resources.

### Observability — below OpenShift AI

Place this panel directly below the compact OpenShift AI panel. Show four rounded sub-rectangles describing the recorded data, collection method, and storage / view. These are side channels, not sequential request stages.

Subtitle: **Recorded data · Collection method · Storage / View**

- **METRICS**
  - **GPU · Latency · Tokens · Cache · Gateway / Guardrail counters**
  - **ServiceMonitor / PodMonitor scrapes → Prometheus**
  - **Thanos queries → Grafana dashboards**
- **REQUEST RECORDS**
  - **Message history per request · Response content · Token usage**
  - **vLLM middleware → HTTP/JSON ingestion API**
- **INFERENCE TRACES**
  - **vLLM inference timing and spans**
  - **OTLP/gRPC → OTel Collector → OTLP/HTTP**
- **GUARDRAIL RECORDS**
  - **Flagged input · Detector results / Scores · Block / Warn action**
  - **Guardrails proxy → HTTP/JSON ingestion API**

Scope note: **Per-request records; full agent / tool trajectories are not linked.**

Prometheus stores time-series metrics; Grafana queries them through OpenShift's Thanos endpoint. Scrapes cover the monitored vLLM, GPU, gateway, router, and guardrails endpoints. The OTel Collector config has a traces pipeline; metrics use Prometheus rather than that collector.

With full I/O capture, the vLLM middleware records the messages or prompt submitted for each local model request, extracted response content, and token usage when returned. It creates a separate trace and generation for each response, including streaming responses, and posts asynchronously to Langfuse's `/api/public/ingestion` endpoint. User, DevSpace, and team metadata are included when their headers reach the middleware. HTTP errors are not emitted as successful I/O records, and ingestion is best-effort.

The middleware does not assign a session ID or link these request records into a complete agent trajectory. Conversation history is captured as submitted on each request; tool execution is not traced. Output extraction may omit structured tool-call fields when text content is present. Do not claim complete agent trajectories, complete tool-call capture, or external-provider capture from this local vLLM instrumentation.

Runtime vLLM spans are sent via OTLP/gRPC to the OTel Collector and forwarded via OTLP/HTTP to Langfuse. These runtime spans are distinct from the middleware's direct I/O ingestion records. Guardrails direct ingestion stores only flagged block / warning outcomes, with input, detector hits and scores, action, and output or block message; it does not record every allowed guardrail check.

Use a dotted **Metrics / Traces / I/O** connection to Observability only. Keep the OpenShift AI capabilities panel free of arrows.

## Footer

Remove the bottom request-flow bar, its numbered stage summary, and its legend text. Keep only the small product-name line below the cluster boundary. Preserve the taller canvas, main numbered stages, and balanced spacing without adding a bottom legend.

## Code references — not image text

- Workspace choices, API URLs, keys, and Continue autocomplete: [workspace helpers](../../charts/pca-devspaces/templates/_helpers.tpl), [DevWorkspace template](../../charts/pca-devspaces/templates/devworkspaces.yaml), and [Continue configuration](../../charts/pca-devspaces/templates/continue-configmaps.yaml).
- Workspace separation and serving-state lifecycle: [namespace RBAC](../../charts/pca-devspaces/templates/rbac.yaml), [per-namespace API-key secrets](../../charts/pca-devspaces/templates/pca-maas-apikey-secrets.yaml), and [retained model-cache PVC](../../charts/pca-ai-serving/templates/pvcs.yaml).
- MaaS listeners, path rules, authentication, token limits, and backend selection: [MaaS Gateway](../../charts/pca-platform-config/templates/maas-gateway.yaml), [front-door rules](../../charts/pca-ai-serving/files/maas-front-door-rules.yaml), [HTTPRoute and policies](../../charts/pca-ai-serving/templates/maas-httproute.yaml), [authentication filter](../../charts/pca-ai-serving/templates/maas-authz-envoyfilter.yaml), and [serving helpers](../../charts/pca-ai-serving/templates/_helpers.tpl).
- Guardrails input-only detector configuration and streaming behavior: [guardrails helpers](../../charts/pca-ai-serving/charts/pca-guardrails/templates/_helpers.tpl) and [proxy implementation](../../charts/pca-ai-serving/charts/pca-guardrails/files/guardrails_proxy.py).
- Semantic Router and external backends: [router configuration](../../charts/pca-ai-serving/templates/semantic-router-config.yaml).
- OpenShift AI capabilities used by PCA: [LLMInferenceService](../../charts/pca-ai-serving/templates/llminferenceservice.yaml), [MaaS resources](../../charts/pca-ai-serving/templates/maas-crs.yaml), [TrustyAI orchestrator](../../charts/pca-ai-serving/charts/pca-guardrails/templates/guardrails-orchestrator.yaml), and [GPU hardware profiles](../../charts/pca-ai-serving/templates/hardware-profiles.yaml).
- Local serving, default route, and optional EPP resources: [LLMInferenceService](../../charts/pca-ai-serving/templates/llminferenceservice.yaml), [llm-d Gateway](../../charts/pca-ai-serving/templates/llm-d-gateway.yaml), [catch-all route](../../charts/pca-ai-serving/templates/llm-d-gateway-httproute.yaml), [EPP](../../charts/pca-ai-serving/templates/llm-d-epp.yaml), and [InferencePool / InferenceModel](../../charts/pca-ai-serving/templates/inference-routing.yaml).
- Defaults and observability: [base values](../../charts/pca-ai-serving/values.yaml), [ROSA overlay](../../charts/pca-ai-serving/values-rosa.yaml), [ARO overlay](../../charts/pca-ai-serving/values-aro.yaml), [existing OpenShift overlay](../../deploy_existing_openshift/values-ai-serving.yaml), and [OTel Collector](../../charts/pca-ai-serving/charts/pca-observability/templates/otel-collector.yaml).
- Recorded I/O and guardrail events: [vLLM middleware](../../charts/pca-ai-serving/files/pca_langfuse_io.py) and [guardrails ingestion](../../charts/pca-ai-serving/charts/pca-guardrails/files/guardrails_langfuse.py). Metrics collection and views: [gateway PodMonitor](../../charts/pca-ai-serving/charts/pca-observability/templates/gateway-podmonitor.yaml), [GPU ServiceMonitor](../../charts/pca-platform-config/templates/nvidia-dcgm-servicemonitor.yaml), [guardrails ServiceMonitor](../../charts/pca-ai-serving/charts/pca-guardrails/templates/guardrails-proxy.yaml), and [Grafana datasource](../../charts/pca-ai-serving/charts/pca-observability/templates/grafana-datasources.yaml).
