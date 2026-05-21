output "resource_group_name" {
  description = "Azure resource group containing the ARO cluster"
  value       = azurerm_resource_group.aro.name
}

output "vnet_id" {
  description = "Azure Virtual Network ID"
  value       = azurerm_virtual_network.aro.id
}

output "get_credentials_command" {
  description = "Command to retrieve ARO kubeadmin credentials via Azure CLI"
  value       = "az aro list-credentials --name ${var.cluster_name} --resource-group ${azurerm_resource_group.aro.name}"
}

output "get_api_url_command" {
  description = "Command to get the ARO API server URL"
  value       = "az aro show --name ${var.cluster_name} --resource-group ${azurerm_resource_group.aro.name} --query apiserverProfile.url -o tsv"
}

output "get_console_url_command" {
  description = "Command to get the ARO web console URL"
  value       = "az aro show --name ${var.cluster_name} --resource-group ${azurerm_resource_group.aro.name} --query consoleProfile.url -o tsv"
}
