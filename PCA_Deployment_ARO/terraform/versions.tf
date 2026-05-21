terraform {
  required_version = ">= 1.4.6"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.0"
    }
  }

  # Uncomment to use remote state (recommended for teams)
  # backend "azurerm" {
  #   resource_group_name  = "pca-terraform-state-rg"
  #   storage_account_name = "pcaterraformstate"
  #   container_name       = "tfstate"
  #   key                  = "aro-pca/terraform.tfstate"
  # }
}

provider "azurerm" {
  subscription_id = var.subscription_id

  features {
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }
}
