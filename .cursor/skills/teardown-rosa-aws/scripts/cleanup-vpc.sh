#!/bin/bash
set -euo pipefail

VPC_ID="${1:?Usage: cleanup-vpc.sh <VPC_ID> <REGION>}"
REGION="${2:?Usage: cleanup-vpc.sh <VPC_ID> <REGION>}"

echo "=== Cleaning up leftover resources in VPC $VPC_ID ($REGION) ==="

echo "--- Deleting ELBv2 load balancers..."
LB_ARNS=$(aws elbv2 describe-load-balancers --region "$REGION" \
	--query "LoadBalancers[?VpcId==\`$VPC_ID\`].LoadBalancerArn" --output text)
for arn in $LB_ARNS; do
	echo "  Deleting LB: $arn"
	aws elbv2 delete-load-balancer --region "$REGION" --load-balancer-arn "$arn"
done

echo "--- Deleting classic ELBs..."
CLB_NAMES=$(aws elb describe-load-balancers --region "$REGION" \
	--query "LoadBalancerDescriptions[?VPCId==\`$VPC_ID\`].LoadBalancerName" --output text)
for name in $CLB_NAMES; do
	echo "  Deleting classic LB: $name"
	aws elb delete-load-balancer --region "$REGION" --load-balancer-name "$name"
done

echo "--- Deleting VPC endpoints..."
VPCE_IDS=$(aws ec2 describe-vpc-endpoints --region "$REGION" \
	--filters "Name=vpc-id,Values=$VPC_ID" \
	--query "VpcEndpoints[].VpcEndpointId" --output text)
for vpce in $VPCE_IDS; do
	echo "  Deleting VPC endpoint: $vpce"
	aws ec2 delete-vpc-endpoints --region "$REGION" --vpc-endpoint-ids "$vpce"
done

echo "--- Terminating EC2 instances..."
INSTANCE_IDS=$(aws ec2 describe-instances --region "$REGION" \
	--filters "Name=vpc-id,Values=$VPC_ID" "Name=instance-state-name,Values=running,pending,stopping,stopped" \
	--query "Reservations[].Instances[].InstanceId" --output text)
if [ -n "$INSTANCE_IDS" ]; then
	echo "  Terminating: $INSTANCE_IDS"
	aws ec2 terminate-instances --region "$REGION" --instance-ids $INSTANCE_IDS >/dev/null
	echo "  Waiting for termination..."
	aws ec2 wait instance-terminated --region "$REGION" --instance-ids $INSTANCE_IDS
	echo "  All instances terminated."
fi

echo "Waiting 15s for ENIs to release..."
sleep 15

echo "--- Detaching and deleting ENIs..."
ENI_IDS=$(aws ec2 describe-network-interfaces --region "$REGION" \
	--filters "Name=vpc-id,Values=$VPC_ID" \
	--query "NetworkInterfaces[].NetworkInterfaceId" --output text)
for eni in $ENI_IDS; do
	ATT_ID=$(aws ec2 describe-network-interfaces --region "$REGION" \
		--network-interface-ids "$eni" \
		--query "NetworkInterfaces[0].Attachment.AttachmentId" --output text 2>/dev/null || echo "None")
	if [ "$ATT_ID" != "None" ] && [ -n "$ATT_ID" ]; then
		echo "  Detaching $eni..."
		aws ec2 detach-network-interface --region "$REGION" --attachment-id "$ATT_ID" --force 2>&1 || true
	fi
done
sleep 10
ENI_IDS=$(aws ec2 describe-network-interfaces --region "$REGION" \
	--filters "Name=vpc-id,Values=$VPC_ID" \
	--query "NetworkInterfaces[].NetworkInterfaceId" --output text)
for eni in $ENI_IDS; do
	echo "  Deleting ENI: $eni"
	aws ec2 delete-network-interface --region "$REGION" --network-interface-id "$eni" 2>&1 || true
done

echo "--- Deleting non-default security groups..."
SG_IDS=$(aws ec2 describe-security-groups --region "$REGION" \
	--filters "Name=vpc-id,Values=$VPC_ID" \
	--query 'SecurityGroups[?GroupName!=`default`].GroupId' --output text)
for sg in $SG_IDS; do
	echo "  Deleting SG: $sg"
	aws ec2 delete-security-group --region "$REGION" --group-id "$sg" 2>&1 || true
done

echo "--- Deleting target groups..."
TG_ARNS=$(aws elbv2 describe-target-groups --region "$REGION" \
	--query "TargetGroups[?VpcId==\`$VPC_ID\`].TargetGroupArn" --output text)
for tg in $TG_ARNS; do
	echo "  Deleting TG: $tg"
	aws elbv2 delete-target-group --region "$REGION" --target-group-arn "$tg" 2>&1 || true
done

echo ""
echo "--- Remaining ENIs:"
aws ec2 describe-network-interfaces --region "$REGION" \
	--filters "Name=vpc-id,Values=$VPC_ID" \
	--query "NetworkInterfaces[].{ID:NetworkInterfaceId,Status:Status}" --output table 2>/dev/null || echo "  None"

echo ""
echo "=== VPC cleanup complete ==="
