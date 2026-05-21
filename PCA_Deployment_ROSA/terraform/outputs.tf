output "cluster_id" {
  description = "ROSA HCP cluster ID"
  value       = rhcs_cluster_rosa_hcp.cluster.id
}

output "cluster_api_url" {
  description = "OpenShift API server URL"
  value       = rhcs_cluster_rosa_hcp.cluster.api_url
}

output "cluster_console_url" {
  description = "OpenShift web console URL"
  value       = rhcs_cluster_rosa_hcp.cluster.console_url
}

output "cluster_domain" {
  description = "Cluster base domain"
  value       = rhcs_cluster_rosa_hcp.cluster.domain
}

output "oidc_endpoint_url" {
  description = "OIDC provider endpoint URL"
  value       = module.oidc_config.oidc_endpoint_url
}

output "gpu_machine_pool_id" {
  description = "GPU machine pool ID"
  value       = var.gpu_pool_enabled ? rhcs_hcp_machine_pool.gpu[0].id : null
}

output "inferentia_machine_pool_id" {
  description = "Inferentia machine pool ID (if enabled)"
  value       = var.inferentia_pool_enabled ? rhcs_hcp_machine_pool.inferentia[0].id : null
}
