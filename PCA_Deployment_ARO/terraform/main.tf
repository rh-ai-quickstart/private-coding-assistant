locals {
  cluster_name = var.cluster_name
  domain       = var.domain != "" ? var.domain : var.cluster_name
  tags = {
    Project     = "private-code-assistant"
    ManagedBy   = "terraform"
    Environment = var.environment
  }
}

# ════════════════════════════════════════════════
# Resource Group
# ════════════════════════════════════════════════
resource "azurerm_resource_group" "aro" {
  name     = "${local.cluster_name}-rg"
  location = var.location
  tags     = local.tags
}

# ════════════════════════════════════════════════
# Virtual Network
# ════════════════════════════════════════════════
resource "azurerm_virtual_network" "aro" {
  name                = "${local.cluster_name}-vnet"
  location            = azurerm_resource_group.aro.location
  resource_group_name = azurerm_resource_group.aro.name
  address_space       = [var.vnet_cidr]
  tags                = local.tags
}

# Master (control plane) subnet — private endpoint policies must be disabled for ARO
resource "azurerm_subnet" "master" {
  name                 = "${local.cluster_name}-master-subnet"
  resource_group_name  = azurerm_resource_group.aro.name
  virtual_network_name = azurerm_virtual_network.aro.name
  address_prefixes     = [var.master_subnet_cidr]

  private_link_service_network_policies_enabled = false
  private_endpoint_network_policies             = "Disabled"

  service_endpoints = ["Microsoft.ContainerRegistry"]
}

# Worker (compute) subnet
resource "azurerm_subnet" "worker" {
  name                 = "${local.cluster_name}-worker-subnet"
  resource_group_name  = azurerm_resource_group.aro.name
  virtual_network_name = azurerm_virtual_network.aro.name
  address_prefixes     = [var.worker_subnet_cidr]

  service_endpoints = ["Microsoft.ContainerRegistry"]
}

# NOTE: ARO creates and manages its own NSG on the subnets.
# Do not pre-attach an NSG to cluster subnets — ARO will reject the create request.

# ════════════════════════════════════════════════
# ARO Cluster via Azure CLI
# az aro create handles service principal creation internally,
# which works for guest users who cannot create AAD app registrations
# directly via the AzureAD Terraform provider.
# ════════════════════════════════════════════════
resource "null_resource" "aro_create" {
  triggers = {
    cluster_name = local.cluster_name
    rg_name      = azurerm_resource_group.aro.name
    vnet_name    = azurerm_virtual_network.aro.name
    version      = var.aro_version
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e

      RG="${azurerm_resource_group.aro.name}"
      CLUSTER="${local.cluster_name}"

      # Idempotency: skip if cluster already exists
      EXISTING=$(az aro list --resource-group "$RG" --query "[?name=='$CLUSTER'].name" -o tsv 2>/dev/null || true)
      if [ -n "$EXISTING" ]; then
        echo "ARO cluster '$CLUSTER' already exists in '$RG'. Skipping creation."
        exit 0
      fi

      echo "Writing pull secret to temp file..."
      PULL_SECRET_FILE="/tmp/pull-secret-$$.json"
      cat > "$PULL_SECRET_FILE" << 'PULLEOF'
${var.pull_secret}
PULLEOF

      echo "Creating ARO cluster: $CLUSTER in $RG ..."
      az aro create \
        --resource-group "$RG" \
        --name "$CLUSTER" \
        --vnet "${azurerm_virtual_network.aro.name}" \
        --master-subnet "${azurerm_subnet.master.name}" \
        --worker-subnet "${azurerm_subnet.worker.name}" \
        --pull-secret "@$PULL_SECRET_FILE" \
        --version "${var.aro_version}" \
        --master-vm-size "${var.master_vm_size}" \
        --worker-vm-size "${var.worker_vm_size}" \
        --worker-count ${var.worker_replicas} \
        --worker-vm-disk-size-gb ${var.worker_disk_size_gb} \
        --pod-cidr "${var.pod_cidr}" \
        --service-cidr "${var.service_cidr}" \
        --apiserver-visibility Public \
        --ingress-visibility Public \
        --no-wait

      rm -f "$PULL_SECRET_FILE"

      echo "ARO cluster creation started. Waiting for it to reach Succeeded state..."
      for i in $(seq 1 90); do
        STATE=$(az aro show --resource-group "$RG" --name "$CLUSTER" \
          --query "provisioningState" -o tsv 2>/dev/null || echo "Unknown")
        echo "  ($i/90) State: $STATE"
        if [ "$STATE" = "Succeeded" ]; then
          echo "ARO cluster is ready!"
          break
        elif [ "$STATE" = "Failed" ]; then
          echo "ERROR: ARO cluster creation failed!"
          az aro show --resource-group "$RG" --name "$CLUSTER" -o json
          exit 1
        fi
        sleep 30
      done
    EOT
  }

  depends_on = [
    azurerm_subnet.master,
    azurerm_subnet.worker,
  ]
}

# ════════════════════════════════════════════════
# Post-Cluster: Login and Grant cluster-admin
# ════════════════════════════════════════════════
resource "null_resource" "oc_login" {
  triggers = {
    cluster_create = null_resource.aro_create.id
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      echo "Retrieving ARO credentials..."

      RG="${azurerm_resource_group.aro.name}"
      CLUSTER="${local.cluster_name}"

      API_URL=$(az aro show --resource-group "$RG" --name "$CLUSTER" \
        --query "apiserverProfile.url" -o tsv)

      KUBEADMIN_PASS=$(az aro list-credentials \
        --name "$CLUSTER" \
        --resource-group "$RG" \
        --query kubeadminPassword -o tsv)

      echo "Logging into ARO cluster: $API_URL ..."
      oc login "$API_URL" \
        --username=kubeadmin \
        --password="$KUBEADMIN_PASS" \
        --insecure-skip-tls-verify=true

      echo "Cluster login successful."
    EOT
  }

  depends_on = [null_resource.aro_create]
}

# ════════════════════════════════════════════════
# GPU MachineSet (A100 — post-cluster provisioning)
# ARO only supports one worker profile at cluster creation.
# GPU nodes are added via MachineSet after the cluster is ready.
# ════════════════════════════════════════════════
resource "null_resource" "gpu_machineset" {
  triggers = {
    cluster_create = null_resource.aro_create.id
    gpu_vm_size    = var.gpu_vm_size
    gpu_replicas   = var.gpu_node_replicas
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      echo "Creating GPU MachineSet for ${var.gpu_vm_size}..."
      chmod +x ${path.module}/../scripts/create-gpu-machineset.sh
      ${path.module}/../scripts/create-gpu-machineset.sh \
        "${var.gpu_vm_size}" \
        "${azurerm_resource_group.aro.name}" \
        "${var.location}" \
        "${var.gpu_node_replicas}"
      echo "GPU MachineSet created."
    EOT
  }

  depends_on = [null_resource.oc_login]
}
