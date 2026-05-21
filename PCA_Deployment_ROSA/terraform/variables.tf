# ──────────────────────────────────────────────
# Authentication
# ──────────────────────────────────────────────
variable "rhcs_token" {
  description = "Red Hat Cloud Services (OCM) offline token. Get from https://console.redhat.com/openshift/token"
  type        = string
  sensitive   = true
}

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-2"
}

variable "environment" {
  description = "Environment name (e.g. dev, staging, prod)"
  type        = string
  default     = "dev"
}

# ──────────────────────────────────────────────
# ROSA HCP Cluster
# ──────────────────────────────────────────────
variable "cluster_name" {
  description = "ROSA HCP cluster name (max 54 characters)"
  type        = string
  default     = "rosa-pca"

  validation {
    condition     = length(var.cluster_name) <= 54
    error_message = "Cluster name must be 54 characters or fewer."
  }
}

variable "openshift_version" {
  description = "OpenShift version (e.g. 4.21.7)"
  type        = string
  default     = "4.21.7"
}

variable "aws_account_id" {
  description = "AWS account ID for the ROSA cluster"
  type        = string
}

variable "aws_billing_account_id" {
  description = "AWS billing account ID (defaults to aws_account_id if not set)"
  type        = string
  default     = ""
}

# ──────────────────────────────────────────────
# Networking
# ──────────────────────────────────────────────
variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets (one per AZ)"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets (one per AZ, needed for NAT gateway)"
  type        = list(string)
  default     = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]
}

variable "availability_zones" {
  description = "AWS Availability Zones"
  type        = list(string)
  default     = ["us-east-2a", "us-east-2b", "us-east-2c"]
}

variable "use_existing_vpc" {
  description = "If true, use existing subnet IDs instead of creating a new VPC"
  type        = bool
  default     = false
}

variable "existing_private_subnet_ids" {
  description = "Existing private subnet IDs (required if use_existing_vpc = true)"
  type        = list(string)
  default     = []
}

# ──────────────────────────────────────────────
# IAM / STS
# ──────────────────────────────────────────────
variable "account_role_prefix" {
  description = "Prefix for ROSA account-wide IAM roles"
  type        = string
  default     = "ManagedOpenShift"
}

variable "operator_role_prefix" {
  description = "Prefix for ROSA operator IAM roles"
  type        = string
  default     = ""
}

# ──────────────────────────────────────────────
# Default Worker Pool
# ──────────────────────────────────────────────
variable "default_worker_instance_type" {
  description = "Instance type for default worker nodes"
  type        = string
  default     = "m5.2xlarge"
}

variable "default_worker_replicas" {
  description = "Number of default worker replicas"
  type        = number
  default     = 3
}

variable "default_worker_autoscaling" {
  description = "Enable autoscaling for default workers"
  type        = bool
  default     = true
}

variable "default_worker_min_replicas" {
  description = "Minimum workers when autoscaling is enabled"
  type        = number
  default     = 3
}

variable "default_worker_max_replicas" {
  description = "Maximum workers when autoscaling is enabled"
  type        = number
  default     = 6
}

# ──────────────────────────────────────────────
# GPU Machine Pool (NVIDIA L40S)
# ──────────────────────────────────────────────
variable "gpu_pool_enabled" {
  description = "Enable GPU machine pool"
  type        = bool
  default     = true
}

variable "gpu_instance_type" {
  description = "Instance type for GPU nodes"
  type        = string
  default     = "g6e.2xlarge"
}

variable "gpu_pool_replicas" {
  description = "Number of GPU nodes"
  type        = number
  default     = 1
}

variable "gpu_pool_autoscaling" {
  description = "Enable autoscaling for GPU pool"
  type        = bool
  default     = false
}

variable "gpu_pool_max_replicas" {
  description = "Max GPU nodes when autoscaling enabled"
  type        = number
  default     = 2
}

# ──────────────────────────────────────────────
# Inferentia Machine Pool (optional)
# ──────────────────────────────────────────────
variable "inferentia_pool_enabled" {
  description = "Enable AWS Inferentia2 machine pool"
  type        = bool
  default     = false
}

variable "inferentia_instance_type" {
  description = "Instance type for Inferentia nodes"
  type        = string
  default     = "inf2.24xlarge"
}

variable "inferentia_pool_replicas" {
  description = "Number of Inferentia nodes"
  type        = number
  default     = 1
}

# ──────────────────────────────────────────────
# DevSpaces Users (HTPasswd IDP)
# ──────────────────────────────────────────────
variable "devspaces_users" {
  description = "List of DevSpaces users to create via HTPasswd IDP"
  type = list(object({
    username = string
    password = string
  }))
  sensitive = true
  default = [
    { username = "dev-user1", password = "" },
    { username = "dev-user2", password = "" },
    { username = "dev-user3", password = "" }
  ]
}

variable "cluster_admin_password" {
  description = "Password for the cluster-admin user (HTPasswd IDP)"
  type        = string
  sensitive   = true
  default     = ""
}

# ──────────────────────────────────────────────
# Secrets
# ──────────────────────────────────────────────
variable "huggingface_token" {
  description = "HuggingFace API token for model downloads"
  type        = string
  sensitive   = true
  default     = ""
}

# ──────────────────────────────────────────────
# GitOps
# ──────────────────────────────────────────────
variable "gitops_repo_url" {
  description = "Git repository URL containing ArgoCD application manifests"
  type        = string
  default     = ""
}

variable "gitops_repo_revision" {
  description = "Git revision (branch/tag) for ArgoCD"
  type        = string
  default     = "main"
}

variable "gitops_repo_path" {
  description = "Path within the Git repo for ArgoCD app-of-apps"
  type        = string
  default     = "PCA_deployment/argocd"
}
