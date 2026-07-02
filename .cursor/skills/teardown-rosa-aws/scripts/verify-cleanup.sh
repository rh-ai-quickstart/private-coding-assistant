#!/bin/bash
set -euo pipefail

TFVARS="/workspace/PCA_Deployment_ROSA/terraform/terraform.tfvars"

if [ ! -f "$TFVARS" ]; then
	echo "ERROR: $TFVARS not found. Pass CLUSTER_NAME and REGION as args."
	echo "Usage: verify-cleanup.sh [cluster_name] [region]"
	exit 1
fi

CLUSTER_NAME="${1:-$(grep '^cluster_name' "$TFVARS" | sed 's/.*= *"\(.*\)"/\1/')}"
REGION="${2:-$(grep '^aws_region' "$TFVARS" | sed 's/.*= *"\(.*\)"/\1/')}"

FAIL=0

check() {
	local label="$1"
	local result="$2"
	if [ -z "$result" ] || [ "$result" = "None" ]; then
		echo "  [OK] $label"
	else
		echo "  [FAIL] $label: $result"
		FAIL=1
	fi
}

echo "=== Verifying teardown of cluster '$CLUSTER_NAME' in $REGION ==="
echo ""

echo "1. VPC"
check "VPC" "$(aws ec2 describe-vpcs --region "$REGION" \
	--filters "Name=tag:Name,Values=${CLUSTER_NAME}-vpc" \
	--query "Vpcs[].VpcId" --output text)"

echo "2. EC2 instances"
check "EC2" "$(aws ec2 describe-instances --region "$REGION" \
	--filters "Name=tag:Name,Values=${CLUSTER_NAME}*" "Name=instance-state-name,Values=running,pending,stopping,stopped" \
	--query "Reservations[].Instances[].InstanceId" --output text)"

echo "3. HCP ROSA IAM roles"
check "IAM roles" "$(aws iam list-roles \
	--query 'Roles[?starts_with(RoleName, `ManagedOpenShift-HCP-ROSA-`)].RoleName' --output text)"

echo "4. Operator IAM roles"
check "Operator roles" "$(aws iam list-roles \
	--query "Roles[?starts_with(RoleName, \`${CLUSTER_NAME}-\`)].RoleName" --output text)"

echo "5. OIDC providers"
check "OIDC" "$(aws iam list-open-id-connect-providers \
	--query 'OpenIDConnectProviderList[?contains(Arn, `openshiftapps.com`)].Arn' --output text)"

echo "6. Load balancers"
check "ELBv2" "$(aws elbv2 describe-load-balancers --region "$REGION" \
	--query "LoadBalancers[?contains(LoadBalancerName, \`${CLUSTER_NAME}\`) || contains(LoadBalancerName, \`k8s\`)].LoadBalancerName" --output text)"

echo "7. NAT gateways"
check "NAT" "$(aws ec2 describe-nat-gateways --region "$REGION" \
	--filter "Name=tag:Name,Values=${CLUSTER_NAME}-nat" \
	--query 'NatGateways[?State!=`deleted`].NatGatewayId' --output text)"

echo "8. Elastic IPs"
check "EIP" "$(aws ec2 describe-addresses --region "$REGION" \
	--filters "Name=tag:Name,Values=${CLUSTER_NAME}-nat-eip" \
	--query "Addresses[].AllocationId" --output text)"

echo "9. Internet gateways"
check "IGW" "$(aws ec2 describe-internet-gateways --region "$REGION" \
	--filters "Name=tag:Name,Values=${CLUSTER_NAME}-igw" \
	--query "InternetGateways[].InternetGatewayId" --output text)"

echo "10. Subnets"
check "Subnets" "$(aws ec2 describe-subnets --region "$REGION" \
	--filters "Name=tag:Name,Values=${CLUSTER_NAME}-*" \
	--query "Subnets[].SubnetId" --output text)"

echo ""
echo "====================================="
if [ "$FAIL" -eq 0 ]; then
	echo "ALL CHECKS PASSED"
else
	echo "SOME CHECKS FAILED (see above)"
fi
echo "====================================="
exit $FAIL
