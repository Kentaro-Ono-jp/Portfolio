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

  owner_principal_arn            = "arn:aws:iam::111122223333:user/ReactorFrontNoel"
  github_oidc_provider_arn       = "arn:aws:iam::111122223333:oidc-provider/token.actions.githubusercontent.com"
  github_oidc_repository_subject = "repo:example-owner/example-repository"
  github_environment             = "aws-deployment"
  github_workflow_name           = "Deploy managed AWS proof"
  github_workflow_ref            = "example-owner/example-repository/.github/workflows/aws-deploy.yml@refs/heads/main"
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
    condition     = length(aws_iam_role.global) == 2 && length(aws_iam_role.environment) == 18
    error_message = "The bootstrap must create two global roles and nine one-purpose roles per explicit environment."
  }

  assert {
    condition = (
      length(aws_codebuild_project.controller) == 4 &&
      length(aws_cloudwatch_log_group.controller) == 4
    )
    error_message = "Each environment must have persistent image and destroy controllers."
  }

  assert {
    condition = (
      length(aws_iam_policy.lifecycle_operator) == 2 &&
      length(aws_iam_policy.lifecycle_destroy) == 2 &&
      length(aws_iam_role_policy_attachment.lifecycle_operator) == 2 &&
      length(aws_iam_role_policy_attachment.lifecycle_destroy) == 2
    )
    error_message = "Each environment must attach separate lifecycle control and destroy policies."
  }

  assert {
    condition = alltrue([
      for key, project in aws_codebuild_project.controller :
      project.auto_retry_limit == (endswith(key, "/destroy") ? 2 : 0)
    ])
    error_message = "Only the destroy controller must retain two automatic retries."
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
      length(local.permissions_boundary_policy) <= 5632 &&
      alltrue([for policy in values(local.global_identity_policies) : length(policy) <= 9728]) &&
      alltrue([for policy in values(local.environment_inline_policies) : length(policy) <= 9728]) &&
      alltrue([for policy in values(local.lifecycle_operator_policies) : length(policy) <= 5632])
    )
    error_message = "Every generated IAM policy must fit its quota and preserve the boundary headroom reserve."
  }

  assert {
    condition = (
      output.github_trust_contract.subject_template_keys == ["repo", "context", "job_workflow_ref", "event_name"] &&
      length(output.github_trust_contract.subjects) == 2 &&
      alltrue([for subject in output.github_trust_contract.subjects : startswith(subject, "repo:example-owner/example-repository:environment:aws-deployment:job_workflow_ref:")])
    )
    error_message = "GitHub trust must connect both allowed events to the customized OIDC subject."
  }

  assert {
    condition = alltrue([
      for key, role in aws_iam_role.environment :
      !endswith(key, "/operator-deployment") || (
        jsondecode(role.assume_role_policy).Statement[0].Sid == "ExactOwnerPrincipal" &&
        jsondecode(role.assume_role_policy).Statement[0].Principal.AWS == var.owner_principal_arn &&
        keys(jsondecode(role.assume_role_policy).Statement[0].Condition) == ["StringEquals"] &&
        jsondecode(role.assume_role_policy).Statement[0].Condition.StringEquals["aws:PrincipalAccount"] == var.aws_account_id
      )
    ])
    error_message = "Human operator trust must accept only the exact same-account owner principal without an MFA condition."
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
