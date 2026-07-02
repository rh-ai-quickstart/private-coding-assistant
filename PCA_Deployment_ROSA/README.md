# Private AI Code Assistant — Automated Deployment

Fully reproducible deployment of an enterprise-grade private AI code assistant on Red Hat OpenShift (ROSA HCP), using **Terraform** for infrastructure provisioning and **ArgoCD (GitOps)** for all on-cluster components.

The end result is a ROSA HCP cluster running:
- **Qwen3-Coder-30B** served via KServe + llm-d with intelligent EPP routing
- **OpenShift Dev Spaces** with pre-configured VS Code extensions (Roo Code, Continue, Cline) consuming the self-hosted model
- All inference traffic stays **cluster-internal** (zero external egress)

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Directory Structure](#directory-structure)
3. [Prerequisites — Tools to Install](#prerequisites--tools-to-install)
4. [Step-by-Step Deployment](#step-by-step-deployment)
   - [Step 1: Install Required Tools](#step-1-install-required-tools)
   - [Step 2: Obtain Required Credentials](#step-2-obtain-required-credentials)
   - [Step 3: Clone and Configure the Repository](#step-3-clone-and-configure-the-repository)
   - [Step 4: Configure Terraform Variables](#step-4-configure-terraform-variables)
   - [Step 5: Initialize Terraform](#step-5-initialize-terraform)
   - [Step 6: Review the Execution Plan](#step-6-review-the-execution-plan)
   - [Step 7: Apply Terraform (Create Infrastructure)](#step-7-apply-terraform-create-infrastructure)
   - [Step 8: Log In to the Cluster](#step-8-log-in-to-the-cluster)
   - [Step 9: Bootstrap ArgoCD (GitOps)](#step-9-bootstrap-argocd-gitops)
   - [Step 10: Monitor ArgoCD Sync](#step-10-monitor-argocd-sync)
   - [Step 11: Set Up the HuggingFace Token](#step-11-set-up-the-huggingface-token)
   - [Step 12: Validate the Deployment](#step-12-validate-the-deployment)
5. [What Gets Deployed](#what-gets-deployed)
6. [Configuration Reference](#configuration-reference)
7. [Day-2 Operations](#day-2-operations)
8. [Secrets Management for Production](#secrets-management-for-production)
9. [Troubleshooting](#troubleshooting)
10. [Component Versions](#component-versions)

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│  Terraform (Phase 1 — Run once)                                  │
│  ├── AWS VPC, Subnets, NAT Gateway                               │
│  ├── ROSA HCP Cluster (STS/OIDC)                                 │
│  ├── Machine Pools (workers, GPU L40S, opt. Inferentia)          │
│  ├── HTPasswd IDP + Developer Users                              │
│  └── OpenShift GitOps Operator + App-of-Apps bootstrap           │
├──────────────────────────────────────────────────────────────────┤
│  ArgoCD App-of-Apps (Phase 2 — Continuous reconciliation)        │
│  ├── Wave 1: Operators (RHOAI, SM, GPU, DevSpaces, certs, LWS)  │
│  ├── Wave 2: Platform Config (Namespaces, DSC, CheCluster, RBAC)│
│  ├── Wave 3: AI Serving (PVCs, TLS, Model Deployment, Gateway)  │
│  └── Wave 4: DevSpaces (ConfigMaps, Workspaces, Extensions)     │
└──────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
PCA_deployment/
├── README.md                              ← You are here
├── terraform/
│   ├── versions.tf                        # Provider pinning (rhcs 1.7.6, aws 5.x)
│   ├── variables.tf                       # All configurable inputs with defaults
│   ├── main.tf                            # VPC, ROSA HCP, machine pools, IDP
│   ├── gitops-bootstrap.tf                # GitOps operator install + App-of-Apps
│   ├── outputs.tf                         # Cluster API URL, console URL, IDs
│   ├── terraform.tfvars.example           # Template (copy to terraform.tfvars)
│   └── .gitignore                         # Prevents secrets from being committed
├── argocd/
│   ├── 00-app-of-apps.yaml               # Root AppProject + 4 child Applications
│   ├── 01-operators/                      # Wave 1: Operator Subscriptions
│   │   ├── subscriptions.yaml             #   RHOAI, SM, GPU, DevSpaces, Serverless
│   │   ├── cert-manager.yaml              #   cert-manager (llm-d-playbook)
│   │   ├── leader-worker-set.yaml         #   LWS (llm-d-playbook)
│   │   ├── nvidia-cluster-policy.yaml     #   GPU stack activation
│   │   └── lws-operator-cr.yaml           #   LWS controller CR
│   ├── 02-platform-config/                # Wave 2: Cluster Configuration
│   │   ├── namespaces.yaml                #   ai-serving, devN-devspaces
│   │   ├── datasciencecluster.yaml        #   KServe "Headed" mode
│   │   ├── checluster.yaml                #   Dev Spaces instance
│   │   ├── rbac.yaml                      #   User → namespace RoleBindings
│   │   └── hf-token-placeholder.yaml      #   HuggingFace secret (placeholder)
│   ├── 03-ai-serving/                     # Wave 3: Model Serving
│   │   ├── llminferenceservice.yaml       #   Qwen3-Coder-30B via LLMInferenceService (llm-d)
│   │   ├── hardware-profiles.yaml         #   Trainium HardwareProfile
│   │   └── vllm-neuron-runtime-template.yaml
│   └── 04-devspaces/                      # Wave 4: Developer Experience
│       ├── vscode-extensions-config.yaml  #   Extension recommendations
│       ├── roo-code-configmaps.yaml       #   Pre-configured Roo Code settings
│       └── devworkspaces.yaml             #   code-workspace-1/2/3 with postStart
└── scripts/
    ├── seal-secret.sh                     # Sealed Secrets helper (production)
    └── validate.sh                        # Post-deployment validation
```

---

## Prerequisites — Tools to Install

You need the following tools installed on your local machine before starting.

| # | Tool | Min Version | Purpose |
|---|------|-------------|---------|
| 1 | Terraform | >= 1.4.6 | Infrastructure provisioning |
| 2 | AWS CLI | v2 | AWS authentication and resource access |
| 3 | `rosa` CLI | latest | ROSA cluster management |
| 4 | `oc` CLI | >= 4.14 | OpenShift cluster interaction |
| 5 | Git | any | Version control / GitOps repository |
| 6 | `kubeseal` | latest (optional) | Sealed Secrets for production |

**Accounts required:**
- **AWS account** with permissions to create VPC, IAM roles, and EC2 instances (including `g6e.2xlarge` GPU instances)
- **Red Hat account** with ROSA entitlement (https://console.redhat.com)
- **HuggingFace account** with an API token for model downloads (https://huggingface.co/settings/tokens)

---

## Step-by-Step Deployment

### Step 1: Install Required Tools

#### 1a. Install Terraform

**macOS (Homebrew):**
```bash
brew tap hashicorp/tap
brew install hashicorp/tap/terraform
terraform version   # Verify: should be >= 1.4.6
```

**Linux (x86_64):**
```bash
sudo yum install -y yum-utils
sudo yum-config-manager --add-repo https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo
sudo yum install -y terraform
terraform version
```

**Windows (Chocolatey):**
```powershell
choco install terraform
terraform version
```

#### 1b. Install AWS CLI v2

**macOS:**
```bash
brew install awscli
aws --version   # Verify: should show aws-cli/2.x.x
```

**Linux:**
```bash
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
aws --version
```

#### 1c. Install ROSA CLI

**macOS:**
```bash
brew install rosa-cli
rosa version
```

**Linux:**
```bash
curl -LO https://mirror.openshift.com/pub/openshift-v4/clients/rosa/latest/rosa-linux.tar.gz
tar xzf rosa-linux.tar.gz
sudo mv rosa /usr/local/bin/
rosa version
```

#### 1d. Install OpenShift CLI (oc)

**macOS:**
```bash
brew install openshift-cli
oc version --client
```

**Linux:**
```bash
curl -LO https://mirror.openshift.com/pub/openshift-v4/clients/ocp/stable/openshift-client-linux.tar.gz
tar xzf openshift-client-linux.tar.gz
sudo mv oc kubectl /usr/local/bin/
oc version --client
```

#### 1e. Verify all tools

Run this to confirm everything is installed:

```bash
echo "--- Terraform ---"  && terraform version
echo "--- AWS CLI ---"    && aws --version
echo "--- ROSA CLI ---"   && rosa version
echo "--- oc CLI ---"     && oc version --client
echo "--- Git ---"        && git --version
```

All five should return version information without errors.

---

### Step 2: Obtain Required Credentials

You need three credentials before proceeding. Gather them now.

#### 2a. AWS credentials

Configure the AWS CLI with an IAM user or role that has administrative access:

```bash
aws configure
```

You will be prompted for:
- **AWS Access Key ID**
- **AWS Secret Access Key**
- **Default region name**: enter `us-east-2`
- **Default output format**: enter `json`

Verify access:
```bash
aws sts get-caller-identity
```

This should return your account ID and ARN. Note the **Account** number — you will need it in Step 4.

#### 2b. Red Hat Cloud Services (OCM) token

1. Open https://console.redhat.com/openshift/token in your browser
2. Click **"Load token"**
3. Copy the full offline token string

Store it temporarily:
```bash
export RHCS_TOKEN="paste-your-token-here"
```

Verify the ROSA CLI can authenticate:
```bash
rosa login --token="${RHCS_TOKEN}"
rosa whoami
```

#### 2c. HuggingFace API token

1. Go to https://huggingface.co/settings/tokens
2. Click **"New token"** → give it a name → select **"Read"** access
3. Copy the token (starts with `hf_`)

Save it — you will use it in Step 4 and Step 11.

---

### Step 3: Clone and Configure the Repository

#### 3a. Fork and clone

Fork this repository to your own GitHub/GitLab account (ArgoCD needs to pull from a Git repo you control), then clone it:

```bash
git clone https://github.com/<your-org>/rosa-llm-driven-deployment.git
cd rosa-llm-driven-deployment/PCA_deployment
```

#### 3b. Set the ArgoCD repository URL

Open `argocd/00-app-of-apps.yaml` and replace every instance of `REPLACE_WITH_GITOPS_REPO_URL` with your forked repository's HTTPS URL:

```bash
# Example using sed (adjust the URL):
sed -i '' 's|REPLACE_WITH_GITOPS_REPO_URL|https://github.com/<your-org>/rosa-llm-driven-deployment.git|g' argocd/00-app-of-apps.yaml
```

Verify:
```bash
grep "repoURL" argocd/00-app-of-apps.yaml
```

All four lines should show your repository URL.

#### 3c. Commit and push

```bash
git add argocd/00-app-of-apps.yaml
git commit -m "Set ArgoCD repo URL for GitOps"
git push origin main
```

---

### Step 4: Configure Terraform Variables

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Open `terraform.tfvars` in your editor and fill in every required value:

```hcl
# REQUIRED — paste your OCM token
rhcs_token = "eyJhbG..."

# REQUIRED — from 'aws sts get-caller-identity'
aws_account_id = "123456789012"

# Cluster settings (defaults are good for most cases)
cluster_name      = "rosa-pca"
openshift_version = "4.21.7"
aws_region        = "us-east-2"

# Worker pool sizing
default_worker_instance_type = "m5.2xlarge"
default_worker_replicas      = 3
default_worker_autoscaling   = true
default_worker_min_replicas  = 3
default_worker_max_replicas  = 6

# GPU pool
gpu_pool_enabled  = true
gpu_instance_type = "g6e.2xlarge"
gpu_pool_replicas = 1

# Inferentia pool (set to true if you have inf2 quota)
inferentia_pool_enabled = false

# REQUIRED — choose a strong password
cluster_admin_password = "YourStr0ngP@ssw0rd!"

# REQUIRED — set passwords for developer users
devspaces_users = [
  { username = "dev-user1", password = "DevPass123!" },
  { username = "dev-user2", password = "DevPass456!" },
]

# REQUIRED — your HuggingFace token
huggingface_token = "hf_..."

# REQUIRED — your forked repo URL
gitops_repo_url      = "https://github.com/<your-org>/rosa-llm-driven-deployment.git"
gitops_repo_revision = "main"
gitops_repo_path     = "PCA_deployment/argocd"
```

**Security note:** `terraform.tfvars` is excluded from Git by the `.gitignore` file. Never commit it.

---

### Step 5: Initialize Terraform

This downloads the required providers (RHCS v1.7.6, AWS, etc.) and modules:

```bash
terraform init
```

Expected output:
```
Initializing the backend...
Initializing provider plugins...
- Finding terraform-redhat/rhcs versions matching "~> 1.7.6"...
- Installing terraform-redhat/rhcs v1.7.6...
...
Terraform has been successfully initialized!
```

If you see errors about provider versions, check your Terraform version (`terraform version` must be >= 1.4.6).

---

### Step 6: Review the Execution Plan

Always review before applying:

```bash
terraform plan -out=tfplan
```

This shows every resource that will be created. Review the output and confirm:
- VPC and subnets are in the correct region
- Cluster name and version are correct
- Machine pool instance types and counts look right
- The number of IDP users matches your expectation

The plan should show approximately **15-25 resources** to create (exact count depends on whether you enabled Inferentia).

---

### Step 7: Apply Terraform (Create Infrastructure)

```bash
terraform apply tfplan
```

**This step takes 30-45 minutes.** It creates resources in this order:

1. **VPC** — subnets, NAT gateway, route tables (~2 minutes)
2. **IAM / OIDC** — STS roles, OIDC provider (~1 minute)
3. **ROSA HCP Cluster** — control plane + initial workers (~25-35 minutes)
4. **Machine Pools** — GPU pool, optional Inferentia (~5 minutes)
5. **HTPasswd IDP** — developer user accounts (~1 minute)
6. **GitOps Bootstrap** — OpenShift GitOps operator + App-of-Apps (~5 minutes)

When complete, Terraform outputs key information:

```
cluster_api_url    = "https://api.rosa-pca.xxxx.p3.openshiftapps.com:443"
cluster_console_url = "https://console-openshift-console.apps.rosa-pca.xxxx.p3.openshiftapps.com"
cluster_id         = "abc123..."
```

Save these URLs.

---

### Step 8: Log In to the Cluster

```bash
# Get the API URL from Terraform output
export API_URL=$(terraform output -raw cluster_api_url)

# Log in with the cluster-admin user you configured
oc login "${API_URL}" \
  --username=cluster-admin \
  --password='YourStr0ngP@ssw0rd!' \
  --insecure-skip-tls-verify=true
```

Verify:
```bash
oc whoami                    # Should show: cluster-admin
oc get nodes                 # Should list worker + GPU nodes
oc get clusterversion        # Should show 4.21.7
```

---

### Step 9: Bootstrap ArgoCD (GitOps)

If Terraform's `gitops_repo_url` variable was set, this step was **already completed automatically** during `terraform apply`. You can verify:

```bash
oc get subscription openshift-gitops-operator -n openshift-gitops-operator
oc get application pca-root -n openshift-gitops
```

If both return results, skip to **Step 10**.

**If you need to bootstrap manually** (e.g., private repo requiring SSH keys):

```bash
# 1. Install OpenShift GitOps operator
oc apply -f - <<'EOF'
apiVersion: v1
kind: Namespace
metadata:
  name: openshift-gitops-operator
---
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: openshift-gitops-operator
  namespace: openshift-gitops-operator
spec: {}
---
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: openshift-gitops-operator
  namespace: openshift-gitops-operator
spec:
  channel: gitops-1.15
  installPlanApproval: Automatic
  name: openshift-gitops-operator
  source: redhat-operators
  sourceNamespace: openshift-marketplace
EOF

# 2. Wait for the operator to install
oc wait --for=condition=Available deployment/openshift-gitops-server \
  -n openshift-gitops --timeout=300s

# 3. Grant ArgoCD cluster-admin
oc apply -f - <<'EOF'
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: openshift-gitops-cluster-admin
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-admin
subjects:
  - kind: ServiceAccount
    name: openshift-gitops-argocd-application-controller
    namespace: openshift-gitops
EOF

# 4. (Optional) If your repo is private, create a repo secret:
oc create secret generic pca-repo \
  -n openshift-gitops \
  --from-literal=url='https://github.com/<your-org>/rosa-llm-driven-deployment.git' \
  --from-literal=username='git' \
  --from-literal=password='ghp_your_personal_access_token'
oc label secret pca-repo -n openshift-gitops argocd.argoproj.io/secret-type=repository

# 5. Apply the App-of-Apps
oc apply -f ../argocd/00-app-of-apps.yaml
```

---

### Step 10: Monitor ArgoCD Sync

ArgoCD now automatically syncs all four waves. This takes **15-30 minutes** (longer if GPU nodes are still scaling).

#### 10a. Open the ArgoCD dashboard

```bash
# Get the ArgoCD URL
ARGOCD_URL=$(oc get route openshift-gitops-server -n openshift-gitops -o jsonpath='{.spec.host}')
echo "https://${ARGOCD_URL}"

# Get the admin password
ARGOCD_PW=$(oc get secret openshift-gitops-cluster -n openshift-gitops -o jsonpath='{.data.admin\.password}' | base64 -d)
echo "Username: admin"
echo "Password: ${ARGOCD_PW}"
```

Open the URL in your browser and log in. You should see four Applications syncing in order.

#### 10b. Monitor from the CLI

```bash
# Watch all ArgoCD applications
watch "oc get applications -n openshift-gitops -o custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status"
```

Expected progression:

| Wave | Application | Sync Status | Health | Approx. Time |
|------|-------------|-------------|--------|---------------|
| 1 | `pca-operators` | Synced | Healthy | ~10 min |
| 2 | `pca-platform-config` | Synced | Healthy | ~5 min |
| 3 | `pca-ai-serving` | Synced | Progressing → Healthy | ~10-15 min |
| 4 | `pca-devspaces` | Synced | Healthy | ~5 min |

Wait until all four show **Synced** and **Healthy**.

#### 10c. Monitor operator installation

```bash
# Check all ClusterServiceVersions
oc get csv -A | grep -E "Succeeded|Installing"

# Wait for a specific operator
oc wait csv -n redhat-ods-operator -l operators.coreos.com/rhods-operator.redhat-ods-operator \
  --for=jsonpath='{.status.phase}'=Succeeded --timeout=600s
```

#### 10d. Monitor model deployment

The model takes the longest — it downloads ~30GB of weights on first deploy:

```bash
# Check the model deployment status
oc get llminferenceservice -n ai-serving

# Watch model pod progress
oc get pods -n ai-serving -w

# Check model download progress (look at init container logs)
oc logs -n ai-serving -l app=qwen3-coder -c storage-initializer --tail=20
```

---

### Step 11: Set Up the HuggingFace Token

The ArgoCD manifests include a placeholder secret for the HuggingFace token. You must replace it with your real token for model downloads to work.

```bash
oc create secret generic hf-token \
  --namespace=ai-serving \
  --from-literal=token='hf_your_actual_token_here' \
  --dry-run=client -o yaml | oc apply -f -
```

Verify:
```bash
oc get secret hf-token -n ai-serving
```

If the model pod was stuck waiting for the token, it will now pick it up and begin downloading.

---

### Step 12: Validate the Deployment

Run the included validation script:

```bash
cd ../scripts
chmod +x validate.sh
./validate.sh
```

This checks 10 categories:
1. Operator installations (all CSVs in `Succeeded` state)
2. DataScienceCluster configuration (KServe `Headed` mode)
3. GPU stack (NVIDIA ClusterPolicy)
4. Namespaces exist
5. CheCluster is Active
6. LLMInferenceService is Ready
7. PVC is Bound
8. llm-d Gateway is Accepted
9. DevWorkspaces are Running
10. ArgoCD Applications are Synced + Healthy

You should see all `[PASS]` results. Any `[WARN]` items may indicate components still starting up — wait a few minutes and re-run.

#### Manual verification

```bash
# Test the model endpoint from within the cluster
oc run curl-test --rm -i --restart=Never --image=curlimages/curl -- \
  -sk https://llm-d-gateway-data-science-gateway-class.ai-serving.svc.cluster.local/v1/models

# Access the Dev Spaces dashboard
echo "Dev Spaces: https://$(oc get route che -n openshift-devspaces -o jsonpath='{.spec.host}')"

# Access the OpenShift console
echo "Console: $(terraform output -raw cluster_console_url)"
```

---

## What Gets Deployed

### Wave 1 — Operators

| Operator | Channel | Namespace |
|----------|---------|-----------|
| Red Hat OpenShift AI (RHOAI) | stable-2.19 | redhat-ods-operator |
| OpenShift Service Mesh | stable | openshift-operators |
| NVIDIA GPU Operator | v24.9 | nvidia-gpu-operator |
| OpenShift Dev Spaces | stable | openshift-devspaces |
| OpenShift Serverless | stable | openshift-serverless |
| cert-manager | (kustomize) | cert-manager |
| LeaderWorkerSet | (kustomize) | lws-system |

### Wave 2 — Platform Configuration

- Namespaces: `ai-serving`, `dev1-devspaces`, `dev2-devspaces`, `dev3-devspaces`
- DataScienceCluster with `rawDeploymentServiceConfig: Headed`
- CheCluster instance in `openshift-devspaces`
- RBAC: each dev user gets `admin` in their devspaces namespace
- HuggingFace token secret (placeholder)

### Wave 3 — AI Serving

- **PVC**: 100Gi `model-cache` on `gp3-csi` (persists model weights across restarts)
- **TLS**: Self-signed cert Job for the llm-d Gateway
- **Model Deployment** (`qwen3-coder`): `Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8` with vLLM args:
  - `--tool-call-parser qwen3_coder --reasoning-parser qwen3`
  - `--max-model-len 32768 --gpu-memory-utilization 0.90`
  - `--enable-prefix-caching --kv-cache-dtype fp8`
  - EPP scorer weights: queue=2, kv-cache=2, prefix-cache=3
- **Gateway + HTTPRoute**: cluster-internal llm-d Gateway with EPP routing
- **HardwareProfile**: Trainium trn1.32xlarge definition
- **ServingRuntime**: vLLM Neuron runtime template for Inferentia/Trainium

### Wave 4 — Developer Workspaces

- VS Code extension recommendations (Roo Code, Continue, Cline)
- Roo Code ConfigMaps per namespace (pre-configured with model endpoint, streaming disabled)
- DevWorkspaces:
  - `code-workspace-1` (dev1): Full setup — Roo Code + Continue + Cline with postStart auto-install
  - `code-workspace-2` (dev2), `code-workspace-3` (dev3): Roo Code only

### Extension Pre-Configuration Details

Each extension connects to the self-hosted model endpoint. Here is exactly what is pre-populated:

| Setting | Value |
|---------|-------|
| **Model Endpoint (Base URL)** | `https://llm-d-gateway-data-science-gateway-class.ai-serving.svc.cluster.local/v1` |
| **Model ID** | `Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8` |
| **API Key** | `EMPTY` (no auth required — cluster-internal) |

| Extension | Auto-Configured? | How | What the User Sees |
|-----------|------------------|-----|---------------------|
| **Roo Code** | Yes | ConfigMap auto-mounted into workspace | Profile named **"Private AI Assistant"** is pre-selected with all modes (architect, code, ask, debug) pointed at the model. Streaming is disabled (required for tool calling). |
| **Continue** | Yes (dev1 only) | `~/.continue/config.yaml` written by postStart script | Model named **"Private AI Assistant"** appears in the chat panel. Tab autocomplete (named **"Private AI Autocomplete"**) is also pre-configured. |
| **Cline** | Installed only (dev1 only) | Extension is installed but requires **manual UI setup** (Cline stores settings in VS Code `globalState`, not in files) | User must open Cline settings and enter: Provider = OpenAI Compatible, Base URL / Model ID / API Key from the table above. |

---

## Configuration Reference

### Terraform Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `cluster_name` | `rosa-pca` | ROSA HCP cluster name (max 54 chars) |
| `openshift_version` | `4.21.7` | OpenShift version |
| `aws_region` | `us-east-2` | AWS region |
| `default_worker_instance_type` | `m5.2xlarge` | Worker node instance type |
| `default_worker_replicas` | `3` | Initial worker count |
| `default_worker_autoscaling` | `true` | Enable worker autoscaling |
| `default_worker_min_replicas` | `3` | Min workers (autoscaling) |
| `default_worker_max_replicas` | `6` | Max workers (autoscaling) |
| `gpu_pool_enabled` | `true` | Create GPU machine pool |
| `gpu_instance_type` | `g6e.2xlarge` | GPU instance type (NVIDIA L40S) |
| `gpu_pool_replicas` | `1` | Number of GPU nodes |
| `inferentia_pool_enabled` | `false` | Create Inferentia machine pool |
| `inferentia_instance_type` | `inf2.24xlarge` | Inferentia instance type |
| `use_existing_vpc` | `false` | Use existing VPC subnets |

### Model Configuration

| vLLM Argument | Value | Purpose |
|---------------|-------|---------|
| `--max-model-len` | `32768` | Context window (tokens) |
| `--gpu-memory-utilization` | `0.90` | GPU memory fraction |
| `--enable-prefix-caching` | — | KV-cache reuse across requests |
| `--enable-auto-tool-choice` | — | Tool/function calling support |
| `--tool-call-parser` | `qwen3_coder` | Tool call format parser |
| `--reasoning-parser` | `qwen3` | Reasoning extraction |
| `--kv-cache-dtype` | `fp8` | Memory-efficient KV-cache |

---

## Day-2 Operations

### Scaling GPU nodes

```bash
# Via Terraform (persistent)
cd terraform
terraform apply -var="gpu_pool_replicas=2"

# Via ROSA CLI (immediate, not persisted in Terraform state)
rosa edit machinepool gpu-l40s --cluster=rosa-pca --replicas=2
```

### Scaling model replicas

Edit `argocd/03-ai-serving/llminferenceservice.yaml` → change `spec.modelSpec.replicas`, commit and push. ArgoCD syncs automatically.

### Adding a new model

1. Create a PVC in `03-ai-serving/pvcs.yaml`
2. Add a new `LLMInferenceService` YAML in `03-ai-serving/`
3. Add HTTPRoute rules in `llm-d-gateway.yaml` for the new InferencePool
4. Update DevSpaces ConfigMaps if extensions should use the new model
5. Commit and push — ArgoCD syncs automatically

### Enabling Inferentia

```bash
terraform apply -var="inferentia_pool_enabled=true"
```

### Adding a new developer user

1. Add to `devspaces_users` in `terraform.tfvars` and run `terraform apply`
2. Add a new namespace + RBAC entry in `02-platform-config/namespaces.yaml` and `rbac.yaml`
3. Add a Roo Code ConfigMap in `04-devspaces/roo-code-configmaps.yaml`
4. Add a DevWorkspace in `04-devspaces/devworkspaces.yaml`
5. Commit and push

---

## Secrets Management for Production

The deployment uses a placeholder for the HuggingFace token. For production environments:

### Option A: Sealed Secrets

```bash
# Install the Sealed Secrets controller
helm repo add sealed-secrets https://bitnami-labs.github.io/sealed-secrets
helm install sealed-secrets -n kube-system sealed-secrets/sealed-secrets

# Seal the HuggingFace secret
echo -n 'hf_your_token' | \
  kubectl create secret generic hf-token \
    --namespace=ai-serving \
    --from-file=token=/dev/stdin \
    --dry-run=client -o yaml | \
  ./scripts/seal-secret.sh /dev/stdin argocd/02-platform-config/hf-token-sealed.yaml

# Commit the sealed secret (safe for Git)
git add argocd/02-platform-config/hf-token-sealed.yaml
git commit -m "Add sealed HuggingFace token"
git push
```

### Option B: External Secrets Operator

1. Install External Secrets Operator via OperatorHub
2. Store secrets in AWS Secrets Manager
3. Create `ExternalSecret` resources that sync to Kubernetes Secrets

---

## Troubleshooting

### Terraform apply fails on ROSA cluster creation

- Verify your OCM token is valid: `rosa login --token="${RHCS_TOKEN}" && rosa whoami`
- Check AWS quotas: GPU instances (`g6e.2xlarge`) require a service limit increase in many accounts
- Ensure the AWS account has ROSA enabled: `rosa verify quota --region=us-east-2`

### ArgoCD application stuck in "OutOfSync" or "Progressing"

```bash
# Check detailed status
oc get application <app-name> -n openshift-gitops -o yaml | grep -A 20 "conditions:"

# Check for CRD ordering issues (common with operators)
oc get events -n openshift-gitops --sort-by=.lastTimestamp | tail -20

# Force a resync
oc patch application <app-name> -n openshift-gitops --type=merge -p '{"operation":{"sync":{}}}'
```

### GPU operator not detecting GPUs

If GPU nodes are present but the GPU operator cannot detect them:

```bash
# Check NFD labels
oc get node <gpu-node> -o json | jq '.metadata.labels | with_entries(select(.key | contains("pci-10de")))'

# Manually add the label if missing
oc label node <gpu-node> feature.node.kubernetes.io/pci-10de.present=true
```

### Model pod stuck in Pending

```bash
# Check scheduling constraints
oc describe pod -n ai-serving -l app=qwen3-coder | grep -A 10 Events

# Verify GPU nodes are ready and have the right taints
oc get nodes -l nvidia.com/gpu.present=true -o wide
oc describe node <gpu-node> | grep -A 5 Taints
```

### DevWorkspace stuck in "Starting"

```bash
# Check the postStart command logs
oc logs -n dev1-devspaces -l controller.devfile.io/devworkspace_name=code-workspace-1 -c dev-tools --tail=100

# Check if the CheCluster is healthy
oc get checluster devspaces -n openshift-devspaces -o jsonpath='{.status.chePhase}'
```

### Model returns empty responses or 502 errors

```bash
# Check if the vLLM server is healthy
oc exec -n ai-serving -it $(oc get pod -n ai-serving -l app=qwen3-coder -o name | head -1) -- curl -sk https://localhost:8000/health

# Check the Gateway and HTTPRoute status
oc get gateway,httproute -n ai-serving
```

---

## Component Versions

| Component | Version | Source |
|-----------|---------|--------|
| ROSA HCP | 4.21.7 | Terraform (RHCS provider) |
| RHOAI | 3.3 | OperatorHub (stable-2.19) |
| KServe | 0.15 | Managed by RHOAI |
| llm-d EPP | 0.4 | Managed by RHOAI |
| vLLM | 0.13.0+rhai11 | RHOAI runtime image |
| Service Mesh | 3.2+ | OperatorHub (stable) |
| NVIDIA GPU Operator | 26.3 | OperatorHub (v24.9) |
| Dev Spaces | 3.27 | OperatorHub (stable) |
| cert-manager | 1.18+ | llm-d-playbook kustomize |
| LeaderWorkerSet | 1.0 | llm-d-playbook kustomize |
| OpenShift GitOps | 1.15 | OperatorHub (gitops-1.15) |
| Terraform RHCS Provider | 1.7.6 | registry.terraform.io |
| Terraform AWS Provider | >= 5.0 | registry.terraform.io |
