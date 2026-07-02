# TODO — Future Improvements

## LLMInferenceService + llm-d Stack (Blocked)

**Status**: Deferred — dependency not available on ROSA  
**Priority**: Medium (upgrade when Red Hat Connectivity Link becomes GA on ROSA)

### What
RHOAI 3.4 provides `LLMInferenceService` (CRD: `serving.kserve.io/v1alpha1`) which is a higher-level
abstraction over standard `InferenceService`. It automatically creates:
- Deployment + Service for the model server
- InferencePool (llm-d)
- EPP (Endpoint Picker Proxy) with smart routing (prefix cache, KV-cache, queue scoring)
- HTTPRoute via Gateway API

### Why it's blocked
`LLMInferenceService` requires **Red Hat Connectivity Link** (Kuadrant + Authorino) to be installed.
Specifically, the DSC reports:
```
ModelsAsServiceReady: False — dependency missing: AuthConfig CRD (authorino.kuadrant.io/v1beta3) not available
KserveLLMInferenceServiceDependencies: False — Red Hat Connectivity Link not installed
```

As of July 2026, Red Hat Connectivity Link is NOT available as a supported operator on ROSA
(only `kuadrant-operator` from Community Operators exists, which doesn't ship the required
AuthConfig CRD).

### Current workaround
Using standard `InferenceService` (serving.kserve.io/v1beta1) with:
- `serving.kserve.io/deploymentMode: RawDeployment`
- Direct container spec with vLLM
- Manual Gateway + HTTPRoute for inference traffic

### When to revisit
- [ ] Check if `connectivity-link-operator` appears in Red Hat Operators catalog
- [ ] Or if RHOAI 3.5+ removes this hard dependency
- [ ] Reference: the original `LLMInferenceService` spec is in git history (commit before this change)

### Additional optional improvements
- [ ] Install Custom Metrics Autoscaler (KEDA) for WVA HPA-based autoscaling
- [ ] Add Inferentia/Trainium machine pool and HardwareProfile once neuron workloads are needed
- [ ] Scale worker pool from 3x m5.xlarge to 4x (cluster is at CPU request capacity)
