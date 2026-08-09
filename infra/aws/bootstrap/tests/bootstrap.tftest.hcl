mock_provider "aws" {
  override_during = plan

  mock_resource "aws_iam_policy" {
    defaults = {
      arn = "arn:aws:iam::111122223333:policy/example-portfolio/example-portfolio-permissions-boundary"
    }
  }
}

variables {
  aws_account_id      = "111122223333"
  aws_partition       = "aws"
  aws_region          = "us-east-1"
  name_prefix         = "example-portfolio"
  repository_identity = "example-owner/example-repository"

  state_bucket_name   = "example-portfolio-111122223333-us-east-1-state"
  bootstrap_state_key = "bootstrap/terraform.tfstate"
  environment_state_keys = {
    manual  = "environments/manual/terraform.tfstate"
    monthly = "environments/monthly/terraform.tfstate"
  }

  owner_principal_arn      = "arn:aws:iam::111122223333:role/PortfolioBootstrapOwner"
  github_oidc_provider_arn = "arn:aws:iam::111122223333:oidc-provider/token.actions.githubusercontent.com"
  github_environment       = "aws-deployment"
  github_workflow_name     = "Deploy managed AWS proof"
  github_workflow_ref      = "example-owner/example-repository/.github/workflows/aws-deploy.yml@refs/heads/main"
}

run "portable_bootstrap_contract" {
  command = plan

  assert {
    condition = (
      aws_s3_bucket_public_access_block.terraform_state.block_public_acls &&
      aws_s3_bucket_public_access_block.terraform_state.block_public_policy &&
      aws_s3_bucket_public_access_block.terraform_state.ignore_public_acls &&
      aws_s3_bucket_public_access_block.terraform_state.restrict_public_buckets
    )
    error_message = "The state bucket must fail closed against every public-access path."
  }

  assert {
    condition     = aws_s3_bucket_versioning.terraform_state.versioning_configuration[0].status == "Enabled"
    error_message = "The state bucket must retain recoverable object versions."
  }

  assert {
    condition     = one(one(aws_s3_bucket_server_side_encryption_configuration.terraform_state.rule).apply_server_side_encryption_by_default).sse_algorithm == "AES256"
    error_message = "The state bucket must enforce server-side encryption."
  }

  assert {
    condition     = length(aws_ecr_repository.application) == 3
    error_message = "Web, API, and ML must have independent ECR repositories."
  }

  assert {
    condition     = alltrue([for repository in aws_ecr_repository.application : repository.image_tag_mutability == "IMMUTABLE"])
    error_message = "Every ECR repository must reject tag replacement."
  }

  assert {
    condition     = length(aws_iam_role.global) == 2 && length(aws_iam_role.environment) == 16
    error_message = "The bootstrap must create two global roles and eight one-purpose roles per explicit environment."
  }

  assert {
    condition = alltrue(concat(
      [for role in aws_iam_role.global : role.permissions_boundary == aws_iam_policy.permissions_boundary.arn],
      [for role in aws_iam_role.environment : role.permissions_boundary == aws_iam_policy.permissions_boundary.arn],
    ))
    error_message = "Every delegable role must carry the fixed permissions boundary."
  }

  assert {
    condition = (
      output.backend_contract.encrypt &&
      output.backend_contract.use_lockfile &&
      output.backend_contract.bootstrap_state_key == "bootstrap/terraform.tfstate" &&
      output.backend_contract.environment_keys.manual == "environments/manual/terraform.tfstate"
    )
    error_message = "Backend output must preserve encryption, S3 locking, and isolated state keys."
  }
}
