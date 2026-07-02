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

Terraform handles `cluster-admin` grant automatically (waits for IDP propagation + retries login). Once apply completes:

```bash
make run CMD="bash -c 'cd PCA_Deployment_ROSA/terraform && terraform output -raw api_url'"
make run CMD="oc login <api-url> --username cluster-admin --password '<password>' --insecure-skip-tls-verify"
make run CMD="oc get nodes"
```

> **Note**: The IDP takes 1-5 minutes to propagate on ROSA HCP. Terraform waits 120s then retries for up to 5 more minutes automatically.

## Common Issues

### IAM roles already exist (EntityAlreadyExists)

Account-level roles may exist from a prior deployment. Import them:

```bash
terraform import 'module.account_iam_resources.aws_iam_role.account_role[0]' ManagedOpenShift-HCP-ROSA-Installer-Role
terraform import 'module.account_iam_resources.aws_iam_role.account_role[1]' ManagedOpenShift-HCP-ROSA-Support-Role
terraform import 'module.account_iam_resources.aws_iam_role.account_role[2]' ManagedOpenShift-HCP-ROSA-Worker-Role
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
