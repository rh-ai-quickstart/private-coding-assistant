locals {
  operator_role_prefix   = var.operator_role_prefix != "" ? var.operator_role_prefix : var.cluster_name
  billing_account_id     = var.aws_billing_account_id != "" ? var.aws_billing_account_id : var.aws_account_id
  private_subnet_ids     = var.use_existing_vpc ? var.existing_private_subnet_ids : aws_subnet.private[*].id
  public_subnet_ids      = var.use_existing_vpc ? [] : aws_subnet.public[*].id
  all_subnet_ids         = concat(local.private_subnet_ids, local.public_subnet_ids)
  rosa_creator_arn       = data.aws_caller_identity.current.arn
}

data "aws_caller_identity" "current" {}

# ════════════════════════════════════════════════
# VPC (created only if use_existing_vpc = false)
# ════════════════════════════════════════════════
resource "aws_vpc" "rosa" {
  count                = var.use_existing_vpc ? 0 : 1
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "${var.cluster_name}-vpc" }
}

resource "aws_internet_gateway" "rosa" {
  count  = var.use_existing_vpc ? 0 : 1
  vpc_id = aws_vpc.rosa[0].id
  tags   = { Name = "${var.cluster_name}-igw" }
}

resource "aws_subnet" "public" {
  count             = var.use_existing_vpc ? 0 : length(var.availability_zones)
  vpc_id            = aws_vpc.rosa[0].id
  cidr_block        = var.public_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = {
    Name                     = "${var.cluster_name}-public-${var.availability_zones[count.index]}"
    "kubernetes.io/role/elb" = "1"
  }
}

resource "aws_subnet" "private" {
  count             = var.use_existing_vpc ? 0 : length(var.availability_zones)
  vpc_id            = aws_vpc.rosa[0].id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = {
    Name                              = "${var.cluster_name}-private-${var.availability_zones[count.index]}"
    "kubernetes.io/role/internal-elb" = "1"
  }
}

resource "aws_eip" "nat" {
  count  = var.use_existing_vpc ? 0 : 1
  domain = "vpc"
  tags   = { Name = "${var.cluster_name}-nat-eip" }
}

resource "aws_nat_gateway" "rosa" {
  count         = var.use_existing_vpc ? 0 : 1
  allocation_id = aws_eip.nat[0].id
  subnet_id     = aws_subnet.public[0].id
  tags          = { Name = "${var.cluster_name}-nat" }

  depends_on = [aws_internet_gateway.rosa]
}

resource "aws_route_table" "public" {
  count  = var.use_existing_vpc ? 0 : 1
  vpc_id = aws_vpc.rosa[0].id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.rosa[0].id
  }
  tags = { Name = "${var.cluster_name}-public-rt" }
}

resource "aws_route_table" "private" {
  count  = var.use_existing_vpc ? 0 : 1
  vpc_id = aws_vpc.rosa[0].id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.rosa[0].id
  }
  tags = { Name = "${var.cluster_name}-private-rt" }
}

resource "aws_route_table_association" "public" {
  count          = var.use_existing_vpc ? 0 : length(var.availability_zones)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public[0].id
}

resource "aws_route_table_association" "private" {
  count          = var.use_existing_vpc ? 0 : length(var.availability_zones)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[0].id
}

# ════════════════════════════════════════════════
# IAM / OIDC for ROSA HCP (STS)
# ════════════════════════════════════════════════
module "account_iam_resources" {
  source = "terraform-redhat/rosa-hcp/rhcs//modules/account-iam-resources"

  account_role_prefix = var.account_role_prefix
}

module "oidc_config" {
  source = "terraform-redhat/rosa-hcp/rhcs//modules/oidc-config-and-provider"

  managed = true
}

module "operator_roles" {
  source = "terraform-redhat/rosa-hcp/rhcs//modules/operator-roles"

  operator_role_prefix = local.operator_role_prefix
  oidc_endpoint_url    = module.oidc_config.oidc_endpoint_url
}

# ════════════════════════════════════════════════
# ROSA HCP Cluster
# ════════════════════════════════════════════════
resource "rhcs_cluster_rosa_hcp" "cluster" {
  name                   = var.cluster_name
  cloud_region           = var.aws_region
  aws_account_id         = var.aws_account_id
  aws_billing_account_id = local.billing_account_id
  aws_subnet_ids         = local.all_subnet_ids
  availability_zones     = var.availability_zones
  version                = var.openshift_version

  properties = {
    rosa_creator_arn = local.rosa_creator_arn
  }

  sts = {
    role_arn         = module.account_iam_resources.account_roles_arn["HCP-ROSA-Installer"]
    support_role_arn = module.account_iam_resources.account_roles_arn["HCP-ROSA-Support"]
    instance_iam_roles = {
      worker_role_arn = module.account_iam_resources.account_roles_arn["HCP-ROSA-Worker"]
    }
    operator_role_prefix = local.operator_role_prefix
    oidc_config_id       = module.oidc_config.oidc_config_id
  }

  replicas = var.default_worker_replicas

  wait_for_create_complete            = true
  wait_for_std_compute_nodes_complete = true

  lifecycle {
    ignore_changes = [availability_zones]
  }
}

resource "rhcs_cluster_wait" "wait" {
  cluster = rhcs_cluster_rosa_hcp.cluster.id
  timeout = 60
}

# ════════════════════════════════════════════════
# Machine Pools
# ════════════════════════════════════════════════

# GPU Machine Pool (NVIDIA L40S — g6e.2xlarge)
resource "rhcs_hcp_machine_pool" "gpu" {
  count   = var.gpu_pool_enabled ? 1 : 0
  cluster = rhcs_cluster_rosa_hcp.cluster.id
  name    = "gpu-l40s"

  subnet_id = local.private_subnet_ids[0]
  auto_repair = true

  aws_node_pool = {
    instance_type = var.gpu_instance_type
  }

  autoscaling = var.gpu_pool_autoscaling ? {
    enabled      = true
    min_replicas = var.gpu_pool_replicas
    max_replicas = var.gpu_pool_max_replicas
  } : {
    enabled      = false
    min_replicas = null
    max_replicas = null
  }

  replicas = var.gpu_pool_autoscaling ? null : var.gpu_pool_replicas

  labels = {
    "nvidia.com/gpu.present"             = "true"
    "node-role.kubernetes.io/gpu"        = ""
    "node.kubernetes.io/instance-type"   = var.gpu_instance_type
  }

  taints = [{
    key           = "nvidia.com/gpu"
    value         = "present"
    schedule_type = "NoSchedule"
  }]

  depends_on = [rhcs_cluster_wait.wait]
}

# Inferentia Machine Pool (optional — inf2.24xlarge)
resource "rhcs_hcp_machine_pool" "inferentia" {
  count   = var.inferentia_pool_enabled ? 1 : 0
  cluster = rhcs_cluster_rosa_hcp.cluster.id
  name    = "inf2-24xl"

  subnet_id = local.private_subnet_ids[0]
  auto_repair = true

  aws_node_pool = {
    instance_type = var.inferentia_instance_type
  }

  autoscaling = {
    enabled = false
  }

  replicas = var.inferentia_pool_replicas

  labels = {
    "node-role.kubernetes.io/inferentia" = ""
    "accelerator"                        = "neuron"
  }

  taints = [{
    key           = "aws.amazon.com/neuroncore"
    value         = "present"
    schedule_type = "NoSchedule"
  }]

  depends_on = [rhcs_cluster_wait.wait]
}

# ════════════════════════════════════════════════
# HTPasswd Identity Provider
# ════════════════════════════════════════════════
resource "rhcs_identity_provider" "htpasswd" {
  cluster = rhcs_cluster_rosa_hcp.cluster.id
  name    = "devspaces-users"

  htpasswd = {
    users = concat(
      var.cluster_admin_password != "" ? [{
        username = "cluster-admin"
        password = var.cluster_admin_password
      }] : [],
      [for u in var.devspaces_users : {
        username = u.username
        password = u.password
      } if u.password != ""]
    )
  }

  depends_on = [rhcs_cluster_wait.wait]
}

# Grant cluster-admin role to the admin user
resource "time_sleep" "wait_for_idp" {
  create_duration = "120s"
  depends_on      = [rhcs_identity_provider.htpasswd]
}

resource "null_resource" "grant_cluster_admin" {
  count = var.cluster_admin_password != "" ? 1 : 0

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      for i in $(seq 1 20); do
        if oc login ${rhcs_cluster_rosa_hcp.cluster.api_url} \
          --username=cluster-admin \
          --password='${var.cluster_admin_password}' \
          --insecure-skip-tls-verify=true 2>/dev/null; then
          echo "Login successful."
          break
        fi
        echo "IDP not ready yet, retrying ($i/20)..."
        sleep 15
      done
      oc adm policy add-cluster-role-to-user cluster-admin cluster-admin
    EOT
  }

  depends_on = [time_sleep.wait_for_idp]
}
