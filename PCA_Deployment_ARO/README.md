# PCA Deployment — Azure Red Hat OpenShift (ARO)

This folder contains Terraform and GitOps (ArgoCD) artifacts to deploy the
**Private AI Code Assistant** on **Azure Red Hat OpenShift (ARO)** with an
NVIDIA A100 GPU node for LLM inference.

---

## Prerequisites

### Tools Required

| Tool | Version | Purpose |
|------|---------|---------|
| `terraform` | >= 1.4.6 | Infrastructure provisioning |
| `az` (Azure CLI) | >= 2.50 | Azure authentication and ARO management |
| `oc` (OpenShift CLI) | >= 4.19 | Cluster interaction and GitOps bootstrap |
| `jq` | >= 1.6 | JSON processing in the GPU MachineSet script |

Install the Azure CLI: `brew install azure-cli` or see [aka.ms/installazurecliwindows](https://aka.ms/installazurecliwindows)

### Azure Permissions Required

Your Azure account needs:

- **Contributor** or **Owner** on the target subscription
- **User Access Administrator** (for role assignments created by `az aro create`)

> **Note:** `az aro create` handles Azure AD App Registration and Service Principal
> creation internally. You do **not** need explicit AAD App Registration permissions.

Register the ARO resource providers if not already registered:

```bash
az provider register --namespace Microsoft.RedHatOpenShift --wait
az provider register --namespace Microsoft.Compute --wait
az provider register --namespace Microsoft.Storage --wait
az provider register --namespace Microsoft.Authorization --wait
```

### GPU Quota

Request quota for `Standard NCADSv4Family` in your target region **before** deployment.
The `Standard_NC24ads_A100_v4` requires 24 vCPUs of this family.

```bash
# Check current quota
az vm list-usage --location centralus -o table | grep -i "Standard NCADSv4"
```

### Red Hat Prerequisites

- A **Red Hat account** with an active OpenShift subscription
- **Pull secret** downloaded from [console.redhat.com/openshift/install/pull-secret](https://console.redhat.com/openshift/install/pull-secret)

---

## Cluster Specifications

| Component | Specification |
|-----------|--------------|
| Platform | Azure Red Hat OpenShift (ARO) |
| OpenShift version | 4.19.24 |
| Azure region | Central US (`centralus`) |
| Master nodes | 3× `Standard_D8s_v5` |
| Worker nodes | 3× `Standard_D8s_v5` |
| GPU nodes | 1× `Standard_NC24ads_A100_v4` (NVIDIA A100 80 GB) |
| RHOAI version | 3.3.2 (`stable-3.x` channel) |
| AI Gateway | llm-d (GA in RHOAI 3.3) |
| Model | `Qwen/Qwen3.6-35B-A3B-FP8` |
| vLLM | 0.17.1 (upstream — see [Post-Deploy vLLM Upgrade](#post-deploy-vllm-0171-upgrade-required)) |
| Storage class | `managed-csi` |

---

## Deployment Steps

### Step 1: Authenticate with Azure

```bash
az login
az account set --subscription "<your-subscription-id>"
```

### Step 2: Configure Terraform Variables

```bash
cd PCA_Deployment_ARO/terraform/
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` and fill in:

| Variable | Description |
|----------|-------------|
| `subscription_id` | Your Azure subscription ID |
| `pull_secret` | Red Hat pull secret (single-line JSON string) |
| `cluster_name` | Cluster name (default: `aro-pca`) |
| `location` | Azure region (default: `centralus`) |
| `aro_version` | OpenShift version (default: `4.19.24`) |
| `gitops_repo_url` | Your fork of the `Private_Code_Assistant` repo |

### Step 3: Deploy Infrastructure with Terraform

```bash
terraform init
terraform plan -out=aro-plan.tfplan
terraform apply aro-plan.tfplan
```

Terraform will execute the following phases:

1. **Resource Group, VNet, and Subnets** — creates the Azure networking foundation.
   Subnets are created without NSGs (ARO manages its own).
2. **ARO Cluster** via `az aro create` — provisions the cluster with 3 master and
   3 worker nodes. Service principal is created automatically. (~35–45 minutes)
3. **Cluster Login** — retrieves kubeadmin credentials and runs `oc login`.
4. **GPU MachineSet** — runs `scripts/create-gpu-machineset.sh` to add the A100 node
   by cloning a worker MachineSet and patching it for Gen2 image support and GPU
   labels/taints. (~5–15 minutes)
5. **OpenShift GitOps Operator** — installs the GitOps operator and grants ArgoCD
   cluster-admin permissions.
6. **ArgoCD App-of-Apps** — deploys the root application (if `gitops_repo_url` is set)
   which triggers all subsequent GitOps-managed resources.

### Step 4: Retrieve Cluster Credentials

```bash
# Get the kubeadmin password
az aro list-credentials \
  --name aro-pca \
  --resource-group aro-pca-rg

# Get the API server URL
az aro show \
  --name aro-pca \
  --resource-group aro-pca-rg \
  --query apiserverProfile.url -o tsv

# Get the web console URL
az aro show \
  --name aro-pca \
  --resource-group aro-pca-rg \
  --query consoleProfile.url -o tsv

# Log in
oc login <API_URL> --username=kubeadmin --password=<PASSWORD>
```

### Step 5: Install Node Feature Discovery (NFD)

NFD is required for the NVIDIA GPU Operator to detect GPU hardware. It is **not**
installed automatically by ArgoCD and must be installed manually:

```bash
# Install the NFD operator
cat <<'EOF' | oc apply -f -
apiVersion: v1
kind: Namespace
metadata:
  name: openshift-nfd
---
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: openshift-nfd
  namespace: openshift-nfd
spec:
  targetNamespaces:
    - openshift-nfd
---
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: nfd
  namespace: openshift-nfd
spec:
  channel: stable
  installPlanApproval: Automatic
  name: nfd
  source: redhat-operators
  sourceNamespace: openshift-marketplace
EOF

# Wait for the operator to install
oc wait --for=condition=Available deployment -l app.kubernetes.io/name=nfd-operator \
  -n openshift-nfd --timeout=300s

# Create the NodeFeatureDiscovery instance
cat <<'EOF' | oc apply -f -
apiVersion: nfd.openshift.io/v1
kind: NodeFeatureDiscovery
metadata:
  name: nfd-instance
  namespace: openshift-nfd
spec:
  instance: ""
  operand:
    image: ""
    servicePort: 12000
  workerConfig:
    configData: ""
EOF
```

### Step 6: Set the HuggingFace Token

The ArgoCD manifests include a placeholder HF token. Replace it with your real token:

```bash
HF_TOKEN_B64=$(echo -n "hf_your_token_here" | base64)

oc patch secret hf-token -n ai-serving \
  --type='json' \
  -p='[{"op":"replace","path":"/data/token","value":"'"${HF_TOKEN_B64}"'"}]'
```

### Step 7: Verify ArgoCD Sync Status

```bash
# Get the ArgoCD admin password
ARGOCD_PASS=$(oc get secret openshift-gitops-cluster -n openshift-gitops \
  -o jsonpath='{.data.admin\.password}' | base64 -d)

# Get the ArgoCD route
ARGOCD_URL=$(oc get route openshift-gitops-server -n openshift-gitops \
  -o jsonpath='{.spec.host}')

echo "ArgoCD UI: https://${ARGOCD_URL}"
echo "Username: admin"
echo "Password: ${ARGOCD_PASS}"
```

Wait for all ArgoCD applications to sync:

```bash
oc get applications -n openshift-gitops
```

Expected applications: `pca-root`, `pca-operators`, `pca-platform-config`,
`pca-ai-serving`, `pca-devspaces`, `leader-worker-set`, `cert-manager`.

---

## Post-Deploy: vLLM 0.17.1 Upgrade (Required)

The `Qwen3.6-35B-A3B-FP8` model uses the `qwen3_5_moe` architecture, which requires
vLLM >= 0.17.0. RHOAI 3.3.2 ships vLLM 0.13.0, so a manual image override is needed.

**This step must be performed after the initial ArgoCD deployment completes and the
LLMInferenceService pod is created (it will be in CrashLoopBackOff).**

```bash
# 1. Scale down the RHOAI operator to prevent reconciliation
oc scale deployment rhods-operator -n redhat-ods-operator --replicas=0

# 2. Scale down the KServe controller
oc scale deployment kserve-controller-manager -n redhat-ods-applications --replicas=0

# 3. Update KServe ConfigMaps to use the upstream vLLM image
#    (prevents reconciliation from reverting the image on pod restarts)
oc patch configmap kserve-parameters -n redhat-ods-applications \
  --type=merge -p '{"data":{"vllmImageTag":"vllm/vllm-openai:v0.17.1"}}'

oc patch configmap odh-model-controller-parameters -n redhat-ods-applications \
  --type=merge -p '{"data":{"vllmImageTag":"vllm/vllm-openai:v0.17.1"}}'

# 4. Patch the vLLM deployment to use the upstream image
oc set image deployment/qwen36-35b-kserve -n ai-serving \
  main=vllm/vllm-openai:v0.17.1

# 5. Set max-model-len and GPU memory utilization
oc set env deployment/qwen36-35b-kserve -n ai-serving \
  VLLM_ADDITIONAL_ARGS="--max-model-len 65536 --gpu-memory-utilization 0.90"

# 6. Wait for the pod to restart and verify it loads successfully
oc rollout status deployment/qwen36-35b-kserve -n ai-serving --timeout=600s
oc logs -f deployment/qwen36-35b-kserve -n ai-serving -c main --tail=50
```

Look for `INFO: Application startup complete` in the logs.

### Delete RHOAI Webhooks (if LLMInferenceService operations fail)

After scaling down the RHOAI operator, some admission webhooks may block operations
on `LLMInferenceService` resources. Delete them if needed:

```bash
oc get validatingwebhookconfigurations,mutatingwebhookconfigurations | grep llmisvc
# Delete any webhooks with "llmisvc" in the name that reference the scaled-down operator
oc delete validatingwebhookconfiguration <name>
oc delete mutatingwebhookconfiguration <name>
```

### Test the Inference Endpoint

```bash
# Via the llm-d AI Gateway (cluster-internal)
GATEWAY_IP=$(oc get svc -n ai-serving \
  -l gateway.networking.k8s.io/gateway-name=llm-d-gateway \
  -o jsonpath='{.items[0].spec.clusterIP}')

curl -sk https://${GATEWAY_IP}/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3.6-35B-A3B-FP8",
    "messages": [{"role": "user", "content": "Write a Python hello world"}],
    "max_tokens": 100
  }'
```

> **Note:** This workaround is unsupported by Red Hat. When RHOAI ships with
> vLLM >= 0.17, this manual step will no longer be necessary.

---

## GitOps Structure

ArgoCD manages the platform in four sync waves:

```
PCA_Deployment_ARO/
├── terraform/                  # Azure infrastructure
│   ├── main.tf                 # RG, VNet, subnets, ARO cluster (via az aro create),
│   │                           # GPU MachineSet, oc login
│   ├── gitops-bootstrap.tf     # OpenShift GitOps operator + App-of-Apps
│   ├── variables.tf            # Input variables with defaults
│   ├── versions.tf             # Provider versions (azurerm ~> 4.0, null >= 3.0)
│   ├── outputs.tf              # Credential retrieval commands
│   └── terraform.tfvars.example
├── argocd/
│   ├── 00-app-of-apps.yaml            # Root ArgoCD application (AppProject + 4 child apps)
│   ├── 01-operators/                   # Wave 1: Operator subscriptions
│   │   ├── subscriptions.yaml          #   RHOAI 3.3.2, Service Mesh 3.x, Serverless,
│   │   │                               #   NVIDIA GPU Operator v24.9, DevSpaces
│   │   ├── nvidia-cluster-policy.yaml  #   GPU Operator ClusterPolicy (DTK driver)
│   │   ├── leader-worker-set.yaml      #   LWS from llm-d-playbook
│   │   ├── lws-operator-cr.yaml        #   LWS operator instance
│   │   └── cert-manager.yaml           #   cert-manager from llm-d-playbook
│   ├── 02-platform-config/             # Wave 2: Platform configuration
│   │   ├── namespaces.yaml             #   ai-serving, dev1/2/3-devspaces
│   │   ├── datasciencecluster.yaml     #   DSC with KServe Headed mode
│   │   ├── checluster.yaml             #   DevSpaces CheCluster instance
│   │   ├── hf-token-placeholder.yaml   #   HuggingFace token secret (placeholder)
│   │   └── rbac.yaml                   #   RoleBindings for dev users
│   ├── 03-ai-serving/                  # Wave 3: AI serving stack
│   │   ├── pvcs.yaml                   #   100Gi model cache (managed-csi)
│   │   ├── llminferenceservice.yaml    #   Qwen3.6-35B-A3B-FP8 on A100
│   │   ├── llm-d-gateway.yaml          #   Gateway + HTTPRoute + DestinationRule
│   │   └── tls-secret-job.yaml         #   Self-signed TLS cert for gateway
│   └── 04-devspaces/                   # Wave 4: Developer workspaces
│       ├── devworkspaces.yaml          #   3× DevWorkspace with VS Code extensions
│       ├── roo-code-configmaps.yaml    #   Roo Code provider config
│       └── vscode-extensions-config.yaml  # VS Code extension recommendations
└── scripts/
    ├── create-gpu-machineset.sh        # Post-cluster A100 node provisioning
    └── validate.sh                     # Post-deployment validation
```

### ArgoCD Applications

| Application | Sync Wave | Content |
|-------------|-----------|---------|
| `pca-operators` | 1 | RHOAI, Service Mesh, Serverless, GPU Operator, DevSpaces subscriptions |
| `pca-platform-config` | 2 | DSC, CheCluster, namespaces, RBAC, HF token |
| `pca-ai-serving` | 3 | LLMInferenceService, llm-d Gateway, model cache PVC, TLS cert |
| `pca-devspaces` | 4 | DevWorkspaces with AI extension configuration |
| `leader-worker-set` | 1 | LWS controller (from `llm-d-playbook`) |
| `cert-manager` | 1 | cert-manager (from `llm-d-playbook`) |

---

## GPU Node Details

The NVIDIA A100 MachineSet is created by `scripts/create-gpu-machineset.sh` after
cluster deployment. The script:

1. Discovers the cluster `infra_id` from the OpenShift infrastructure object
2. Clones an existing worker MachineSet as a template
3. Patches it for `Standard_NC24ads_A100_v4` with **Gen2 image SKU** (required for A100)
4. Adds GPU labels (`nvidia.com/gpu.present=true`) and taints (`nvidia.com/gpu:NoSchedule`)
5. Applies the new MachineSet and waits for the node to become ready

The Gen2 image SKU is derived dynamically from the existing worker SKU
(e.g., `aro_419` → `419-v2`). A100 VMs require Hyper-V Generation 2.

### Scaling GPU Nodes

```bash
# Scale to 0 (stop GPU billing)
oc scale machineset <infra_id>-gpu-a100 -n openshift-machine-api --replicas=0

# Scale back to 1
oc scale machineset <infra_id>-gpu-a100 -n openshift-machine-api --replicas=1

# Monitor
oc get machineset -n openshift-machine-api
oc get nodes -l nvidia.com/gpu.present=true
```

---

## AI Gateway Configuration

The llm-d AI Gateway uses an Istio `Gateway` with a self-signed TLS certificate.
The `HTTPRoute` forwards `/v1/*` traffic directly to the vLLM workload `Service`
(not via `InferencePool`), which is necessary for compatibility with the custom
vLLM 0.17.1 runtime.

An Istio `DestinationRule` provides TLS origination to the vLLM backend, which
serves over HTTPS using KServe-injected certificates.

**Cluster-internal endpoint:**

```
https://llm-d-gateway-data-science-gateway-class.ai-serving.svc.cluster.local/v1
```

---

## DevSpaces + AI Extensions

Each developer workspace includes VS Code in the browser with:

| Extension | Configuration |
|-----------|--------------|
| **Continue** | Pre-configured via ConfigMap (`config.yaml` mounted at `/home/user/.continue`) |
| **Roo Code** | Pre-configured via ConfigMap (`provider_profiles.json` with OpenAI-compatible provider) |
| **Cline** | Requires one-time manual configuration in the UI (settings stored in VS Code globalState) |

### Cline Manual Setup

In the Cline extension UI, configure:

| Field | Value |
|-------|-------|
| Provider | OpenAI Compatible |
| Base URL | `https://llm-d-gateway-data-science-gateway-class.ai-serving.svc.cluster.local/v1` |
| Model | `Qwen/Qwen3.6-35B-A3B-FP8` |
| API Key | _(leave empty)_ |

---

## Destroying the Cluster

```bash
# Delete the ARO cluster (takes 15-20 minutes)
az aro delete --name aro-pca --resource-group aro-pca-rg --yes

# After cluster deletion, clean up the resource group
az group delete --name aro-pca-rg --yes --no-wait

# Or use Terraform (if state file is available)
cd PCA_Deployment_ARO/terraform/
terraform destroy
```

---

## Troubleshooting

**ARO cluster creation fails with "InsufficientQuota":**
Request `Standard NCADSv4Family` quota in your target region via
Azure Portal → Quotas → Compute. The `Standard_NC24ads_A100_v4` requires 24 vCPUs.

**GPU node stuck in Provisioning:**
Check for Gen2 image SKU issues — A100 VMs require Hyper-V Generation 2.
The MachineSet script handles this automatically, but verify with:
```bash
oc describe machine -n openshift-machine-api | grep -A 10 "Message"
```

**NVIDIA GPU driver pods not scheduling:**
Ensure NFD (Node Feature Discovery) is installed and the `NodeFeatureDiscovery` CR
exists. Without NFD, the GPU Operator cannot detect GPU hardware.

**vLLM pod CrashLoopBackOff with "qwen3_5_moe" error:**
This means the vLLM 0.17.1 upgrade was not applied. Follow the
[Post-Deploy vLLM Upgrade](#post-deploy-vllm-0171-upgrade-required) steps.

**vLLM pod OOM-killed (exit code 137):**
Reduce `--max-model-len` in `VLLM_ADDITIONAL_ARGS`. With 90% GPU memory utilization,
65536 tokens fits on A100 80 GB. The model's default 262144 context will OOM.

**AI Gateway returns "upstream connect error":**
Verify the `DestinationRule` for TLS origination exists in the `ai-serving` namespace.
The vLLM backend serves over HTTPS (KServe-injected certs), so the gateway must
originate TLS to the backend.

**NSG error during ARO cluster creation:**
ARO requires subnets with no pre-attached Network Security Groups. If you see
"A Network Security Group is already assigned to this subnet", detach the NSG
from both subnets before retrying.

**LLMInferenceService operations blocked by webhooks:**
After scaling down the RHOAI operator, admission webhooks may block create/delete
operations on `LLMInferenceService` resources. Delete the stale webhooks:
```bash
oc get validatingwebhookconfigurations,mutatingwebhookconfigurations | grep llmisvc
oc delete validatingwebhookconfiguration <name>
```
