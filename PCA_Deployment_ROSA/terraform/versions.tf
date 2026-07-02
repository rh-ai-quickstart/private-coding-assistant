terraform {
  required_version = ">= 1.4.6"

  required_providers {
    rhcs = {
      source  = "terraform-redhat/rhcs"
      version = "~> 1.7.6"
    }
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.0"
    }
    time = {
      source  = "hashicorp/time"
      version = ">= 0.9"
    }
  }

  # Uncomment to use remote state (recommended for teams)
  # backend "s3" {
  #   bucket         = "pca-terraform-state"
  #   key            = "rosa-hcp/terraform.tfstate"
  #   region         = "us-east-2"
  #   dynamodb_table = "pca-terraform-locks"
  #   encrypt        = true
  # }
}

provider "rhcs" {
  token = var.rhcs_token
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "private-code-assistant"
      ManagedBy   = "terraform"
      Environment = var.environment
    }
  }
}
