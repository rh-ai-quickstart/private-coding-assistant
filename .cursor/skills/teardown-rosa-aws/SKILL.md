---
name: teardown-rosa-aws
description: >-
  Tear down a ROSA HCP cluster on AWS, clean up leftover resources, and verify
  complete removal. Use when the user asks to teardown, destroy, delete, remove,
  or clean up a ROSA cluster, or mentions terraform destroy, make run destroy,
  or AWS resource cleanup for this project.
disable-model-invocation: true
---

# Tear Down ROSA HCP on AWS

## Prerequisites

- `.env` with valid AWS credentials and `RHCS_TOKEN`
- Provisioner container image built (`make build`)
- Terraform state present in `PCA_Deployment_ROSA/terraform/`

## Workflow

### Step 1: Confirm terraform state has resources

```bash
make run CMD="bash -c 'cd /workspace/PCA_Deployment_ROSA/terraform && terraform state list'"
```

If empty, skip to **Step 5: Verify** to check for orphaned AWS resources.

### Step 2: Run terraform destroy

```bash
make run CMD="bash -c 'cd /workspace/PCA_Deployment_ROSA/terraform && terraform init -upgrade && terraform destroy -auto-approve'"
```

This typically takes 15-30 minutes. Monitor for completion.

**If destroy completes successfully**, skip to **Step 5: Verify**.

### Step 3: Handle stuck VPC deletion

`terraform destroy` commonly gets stuck on VPC resources (subnets, internet gateway) because ROSA leaves behind unmanaged resources. If the IGW or subnets are stuck destroying for >5 minutes:

1. Kill the stuck container: `podman kill pca; podman rm pca`

2. Get the VPC ID from state:
   ```bash
   make run CMD="bash -c 'cd /workspace/PCA_Deployment_ROSA/terraform && terraform state show aws_vpc.rosa[0]'"
   ```

3. Run the cleanup script (substitute `VPC_ID` and `REGION`):
   ```bash
   make run CMD="bash /workspace/.cursor/skills/teardown-rosa-aws/scripts/cleanup-vpc.sh <VPC_ID> <REGION>"
   ```

   This script removes, in order:
   - ELBv2 and classic load balancers
   - VPC endpoints
   - EC2 instances (terminates and waits)
   - ENIs (detach + delete)
   - Non-default security groups
   - Target groups

4. Re-run terraform destroy:
   ```bash
   make run CMD="bash -c 'cd /workspace/PCA_Deployment_ROSA/terraform && terraform destroy -auto-approve'"
   ```

### Step 4: Clean up orphaned OIDC providers

ROSA may leave behind OIDC providers from current or previous deployments:

```bash
make run CMD="bash -c 'aws iam list-open-id-connect-providers --query \"OpenIDConnectProviderList[?contains(Arn, \\\`openshiftapps.com\\\`)].Arn\" --output text'"
```

Delete any found:

```bash
make run CMD="bash -c 'aws iam delete-open-id-connect-provider --open-id-connect-provider-arn <ARN>'"
```

### Step 5: Verify complete cleanup

Run the verification script (reads cluster name and region from `terraform.tfvars`):

```bash
make run CMD="bash /workspace/.cursor/skills/teardown-rosa-aws/scripts/verify-cleanup.sh"
```

All 10 checks must pass. If any fail, delete the offending resources manually and re-verify.

### Step 6: Confirm terraform state is empty

```bash
make run CMD="bash -c 'cd /workspace/PCA_Deployment_ROSA/terraform && terraform state list'"
```

Should return no output.

## Common Issues

### Container name conflict

```bash
podman kill pca; podman rm pca
```

### Subnets stuck deleting

Usually caused by leftover ENIs from EC2 instances. Check for running instances:

```bash
make run CMD="bash -c 'aws ec2 describe-instances --region <REGION> --filters Name=vpc-id,Values=<VPC_ID> Name=instance-state-name,Values=running,pending,stopping,stopped --query \"Reservations[].Instances[].{ID:InstanceId,Name:Tags[?Key==\\\`Name\\\`].Value|[0]}\" --output table'"
```

Terminate them and wait before retrying.

### IGW stuck deleting

Usually caused by leftover NLBs. Check:

```bash
make run CMD="bash -c 'aws elbv2 describe-load-balancers --region <REGION> --query \"LoadBalancers[?VpcId==\\\`<VPC_ID>\\\`].LoadBalancerArn\" --output text'"
```

## Timing

| Phase | Duration |
|-------|----------|
| Terraform destroy (cluster + IAM) | 10-20 min |
| VPC cleanup (if stuck) | 5-10 min |
| VPC destroy (after cleanup) | ~15 sec |
| Verification | ~15 sec |
| **Total** | **~15-30 min** |
