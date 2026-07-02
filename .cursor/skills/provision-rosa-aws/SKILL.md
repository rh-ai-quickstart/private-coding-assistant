---
name: provision-rosa-aws
description: >-
  Provision a ROSA HCP cluster on AWS using the containerized provisioner and
  Terraform. Use when the user asks to deploy, provision, create, or spin up a
  ROSA cluster, or mentions AWS provisioning, make build, make shell, or
  terraform apply for this project.
disable-model-invocation: true
---

# Provision ROSA HCP on AWS

## Prerequisites

- AWS credentials (Access Key ID, Secret Access Key, Account ID, Region)
- Red Hat OCM token from https://console.redhat.com/openshift/token
- HuggingFace token for model access
- Podman installed on the host

## Workflow

### Step 1: Configure credentials

Update `.env`:

```
AWS_ACCESS_KEY_ID=<key>
AWS_SECRET_ACCESS_KEY=<secret>
AWS_ACCOUNT_ID=<account-id>
AWS_DEFAULT_REGION=us-east-2
RHCS_TOKEN=<ocm-token>
HUGGINGFACE_TOKEN=<hf-token>
CLUSTER_ADMIN_PASSWORD=<password>
```

Update `PCA_Deployment_ROSA/terraform/terraform.tfvars`:
- Set `aws_account_id`, `rhcs_token`, `huggingface_token`, `cluster_admin_password`
- Adjust cluster config as needed (name, version, instance types)

### Step 2: Build the provisioner container

```bash
make build
```

### Step 3: Run Terraform

```bash
make run CMD="bash -c 'cd PCA_Deployment_ROSA/terraform && terraform init'"
make run CMD="bash -c 'cd PCA_Deployment_ROSA/terraform && terraform plan -out=tfplan'"
make run CMD="bash -c 'cd PCA_Deployment_ROSA/terraform && terraform apply tfplan'"
```

If container name conflicts: `podman rm -f pca`

### Step 4: Verify cluster access

Terraform uses `rosa create admin` (via OCM API) to create the cluster-admin user. After apply completes, wait 2-5 minutes for IDP propagation:

```bash
make run CMD="bash -c 'cd PCA_Deployment_ROSA/terraform && terraform output -raw api_url'"
make run CMD="oc login <api-url> --username cluster-admin --password '<password>' --insecure-skip-tls-verify"
make run CMD="oc get nodes"
```

> **Note**: The admin IDP takes 2-5 minutes to propagate on ROSA HCP. Terraform waits 120s before attempting the grant.

## Common Issues

### Duplicate cluster name

OCM rejects cluster creation if the name already exists in your org. Either choose a different `cluster_name` in tfvars or delete the old cluster first.

### Invalid number of compute nodes

`default_worker_replicas` must be a multiple of the number of private subnets (default: 3). E.g. use 3, 6, 9.

### IAM roles already exist (EntityAlreadyExists)

Account-level roles may exist from a prior deployment. Import them:

```bash
terraform import 'module.account_iam_resources.aws_iam_role.account_role[0]' ManagedOpenShift-HCP-ROSA-Installer-Role
terraform import 'module.account_iam_resources.aws_iam_role.account_role[1]' ManagedOpenShift-HCP-ROSA-Support-Role
terraform import 'module.account_iam_resources.aws_iam_role.account_role[2]' ManagedOpenShift-HCP-ROSA-Worker-Role
```

### OAuth 500 — identity mapping conflict

The username `cluster-admin` is reserved for `rosa create admin`. **Never** add it to custom HTPasswd IDPs. If you hit a 500 with "cannot be claimed by identity", fix via OCM API:

```bash
rosa delete admin --cluster=<id> --yes
# Create IDP with mapping_method "add" to bypass stale mapping:
ACCESS_TOKEN=$(curl -s -X POST "https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token" \
  -d "grant_type=refresh_token&client_id=cloud-services&refresh_token=$RHCS_TOKEN" | jq -r .access_token)
curl -X POST "https://api.openshift.com/api/clusters_mgmt/v1/clusters/<cluster-id>/identity_providers" \
  -H "Authorization: Bearer $ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d '{"type":"HTPasswdIdentityProvider","name":"cluster-admin","mapping_method":"add","htpasswd":{"users":{"items":[{"username":"cluster-admin","password":"<pw>"}]}}}'
# Then grant cluster-admin group:
curl -X POST "https://api.openshift.com/api/clusters_mgmt/v1/clusters/<cluster-id>/groups/cluster-admins/users" \
  -H "Authorization: Bearer $ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d '{"id":"cluster-admin"}'
```

### OCM 500 error during cluster creation

Transient server error. Wait a minute and re-run `terraform apply`.

## Timing

| Phase | Duration |
|-------|----------|
| VPC + Networking + IAM | ~2 min |
| ROSA HCP Cluster | 25-40 min |
| GPU Machine Pool + IDP | ~30 sec |
| IDP propagation + cluster-admin grant | ~2-5 min |
| **Total** | **~30-48 min** |

## Verification

```bash
rosa describe cluster --cluster=<name>
oc login <api-url> --username cluster-admin --password <password>
oc get nodes
```
