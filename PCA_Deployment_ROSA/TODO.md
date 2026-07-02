# TODO — Future Improvements

## LLMInferenceService + llm-d Stack (Deployed)

**Status**: Deployed via `LLMInferenceService` (serving.kserve.io/v1alpha2)  
**Auth**: Disabled via `security.opendatahub.io/enable-auth: "false"` (Connectivity Link not yet on ROSA)

### What's deployed
- `LLMInferenceService` CRD manages vLLM runtime, EPP router, and Gateway API routing
- GPU Operator upgraded to v25.3 channel (CUDA 12.9+ driver support)
- Old workaround removed (manual ServingRuntime + InferenceService + Gateway + TLS job)

### When to revisit auth
- [ ] Check if `connectivity-link-operator` appears in Red Hat Operators catalog on ROSA
- [ ] Or if RHOAI 3.5+ removes the hard Connectivity Link dependency
- [ ] When available, remove the `enable-auth: "false"` annotation to enable Authorino auth

### Optional improvements
- [ ] Install Custom Metrics Autoscaler (KEDA) for WVA HPA-based autoscaling
- [ ] Add Inferentia/Trainium machine pool and HardwareProfile once neuron workloads are needed
- [ ] Scale worker pool from 3x m5.xlarge to 4x (cluster is at CPU request capacity)
