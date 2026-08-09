terraform {
  required_version = "= 1.15.8"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.58.0"
    }
  }

  # The initial local apply creates the backend bucket. The repository-owned
  # preparation script then adds an ignored partial S3 backend declaration and
  # migrates this same state into the explicit bootstrap key.
}

provider "aws" {
  region              = var.aws_region
  allowed_account_ids = [var.aws_account_id]

  default_tags {
    tags = local.common_tags
  }
}
