# ──────────────────────────────────────────────
# Azure Authentication
# ──────────────────────────────────────────────
variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
}

variable "environment" {
  description = "Environment name (e.g. dev, staging, prod)"
  type        = string
  default     = "dev"
}

# ──────────────────────────────────────────────
# ARO Cluster
# ──────────────────────────────────────────────
variable "cluster_name" {
  description = "ARO cluster name (max 54 characters)"
  type        = string
  default     = "aro-pca"

  validation {
    condition     = length(var.cluster_name) <= 54
    error_message = "Cluster name must be 54 characters or fewer."
  }
}

variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "australiaeast"
}

variable "aro_version" {
  description = "OpenShift version for ARO cluster (e.g. 4.19.24)"
  type        = string
  default     = "4.19.24"
}

variable "pull_secret" {
  description = "Red Hat pull secret (JSON string). Get from https://console.redhat.com/openshift/install/pull-secret"
  type        = string
  sensitive   = true
  default     = ""
}

variable "domain" {
  description = "Custom domain prefix for the cluster (leave empty for auto-generated)"
  type        = string
  default     = ""
}

# ──────────────────────────────────────────────
# Networking
# ──────────────────────────────────────────────
variable "vnet_cidr" {
  description = "CIDR block for the Azure Virtual Network"
  type        = string
  default     = "10.0.0.0/8"
}

variable "master_subnet_cidr" {
  description = "CIDR block for the ARO master (control plane) subnet"
  type        = string
  default     = "10.0.0.0/23"
}

variable "worker_subnet_cidr" {
  description = "CIDR block for the ARO worker (compute) subnet"
  type        = string
  default     = "10.0.2.0/23"
}

variable "pod_cidr" {
  description = "CIDR block for pod network"
  type        = string
  default     = "10.128.0.0/14"
}

variable "service_cidr" {
  description = "CIDR block for service network"
  type        = string
  default     = "172.30.0.0/16"
}

# ──────────────────────────────────────────────
# Default Worker Pool
# ──────────────────────────────────────────────
variable "worker_vm_size" {
  description = "VM size for default worker nodes"
  type        = string
  default     = "Standard_D8s_v5"
}

variable "worker_replicas" {
  description = "Number of default worker nodes"
  type        = number
  default     = 3
}

variable "worker_disk_size_gb" {
  description = "OS disk size in GB for worker nodes"
  type        = number
  default     = 128
}

# ──────────────────────────────────────────────
# GPU Machine Pool (NVIDIA H100)
# ──────────────────────────────────────────────
variable "gpu_vm_size" {
  description = "Azure VM size for GPU nodes (H100 NVL 94 GB)"
  type        = string
  default     = "Standard_NC40ads_H100_v5"
}

variable "gpu_node_replicas" {
  description = "Number of GPU nodes to provision via MachineSet after cluster creation"
  type        = number
  default     = 1
}

# ──────────────────────────────────────────────
# Master Nodes
# ──────────────────────────────────────────────
variable "master_vm_size" {
  description = "VM size for ARO master (control plane) nodes"
  type        = string
  default     = "Standard_D8s_v5"
}

# ──────────────────────────────────────────────
# DevSpaces Users
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
  description = "Password for the cluster-admin user"
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
  default     = "PCA_Deployment_ARO/argocd"
}
