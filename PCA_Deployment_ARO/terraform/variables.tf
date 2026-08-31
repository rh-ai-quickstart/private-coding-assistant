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
  default     = "aro-pca-aue"

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
  description = "OpenShift version for ARO cluster"
  type        = string
  default     = "4.20.15"
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
# Model Selection
# ──────────────────────────────────────────────
variable "model_variant" {
  description = "Which coding model to deploy on the GPU pool: qwen3.6 (Qwen3.6-35B-A3B-FP8, sparse MoE) or qwen3.8 (Qwen3.8-27B-FP8, dense, Apache-2.0). Only one model runs at a time — this automation does not support serving both concurrently behind the same AI Gateway, which triggers a known Kuadrant EnvoyFilter-ordering bug that OOM-crashes llm-d-gateway."
  type        = string
  default     = "qwen3.6"

  validation {
    condition     = contains(["qwen3.6", "qwen3.8"], var.model_variant)
    error_message = "model_variant must be one of: qwen3.6, qwen3.8."
  }
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
  description = "HTPasswd DevSpaces users (username + password). List length is how many users — there is no separate count/N variable. Passwords must be set by the operator (not generated). Prefer usernames like dev-user1 with Helm namespace <username>-devspaces."
  type = list(object({
    username = string
    password = string
  }))
  sensitive = true
  default = [
    { username = "dev-user1", password = "" },
    { username = "dev-user2", password = "" }
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
  description = "HuggingFace API token for model downloads. Required when semantic_router_enabled is true (local Qwen + MiniLM)."
  type        = string
  sensitive   = true
  default     = ""
}

variable "semantic_router_enabled" {
  description = "When true, set both Helm Semantic Router flags on pca-ai-serving. null (default) leaves the chart overlay in charge (ROSA on, ARO off). true requires huggingface_token."
  type        = bool
  default     = null
  nullable    = true
}

variable "semantic_router_models_json" {
  description = "JSON array of extra OpenAI-compatible backends. Do not list local Qwen. Empty [] pins chat to the injected local model."
  type        = string
  default     = "[]"

  validation {
    condition     = can(jsondecode(var.semantic_router_models_json))
    error_message = "semantic_router_models_json must be valid JSON."
  }
}

variable "semantic_router_api_keys_json" {
  description = "JSON object mapping extra model name to API key. Never commit this. Required for each extra in semantic_router_models_json."
  type        = string
  sensitive   = true
  default     = "{}"

  validation {
    condition     = can(jsondecode(var.semantic_router_api_keys_json))
    error_message = "semantic_router_api_keys_json must be valid JSON."
  }
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
  description = "Path within the Git repo to the pca-app-of-apps Helm chart"
  type        = string
  default     = "PCA_Deployment_ARO/charts/pca-app-of-apps"
}

variable "gitops_charts_path" {
  description = "Base path within the Git repo for sibling Helm charts"
  type        = string
  default     = "PCA_Deployment_ARO/charts"
}
