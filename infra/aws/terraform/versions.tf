terraform {
  required_version = ">= 1.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.0"
    }
  }

  # Remote state in S3 + DynamoDB locking
  # Uncomment and set bucket/table after bootstrapping:
  # backend "s3" {
  #   bucket         = "my-rag-tfstate"
  #   key            = "rag-engine/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "rag-tfstate-lock"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "rag-engine"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
