terraform {
  required_version = "= 1.15.8"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.58.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "= 3.7.2"
    }
  }

  # Step 5 supplies an ignored partial S3 backend declaration bound to the
  # exact environment_state_key. Keeping it generated lets static plan proof
  # use a local backend without ever reading bootstrap remote state.
}

provider "aws" {
  region = var.aws_region

  # These settings keep static plan proof AWS-free. Apply credentials remain
  # external and Step 5 must preflight their exact account and role identity.
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_region_validation      = true
  skip_requesting_account_id  = true

  default_tags {
    tags = local.ownership_tags
  }
}
