locals {
  role_path             = "/${var.name_prefix}/"
  iam_prefix            = "arn:${var.aws_partition}:iam::${var.aws_account_id}"
  state_bucket_arn      = "arn:${var.aws_partition}:s3:::${var.state_bucket_name}"
  boundary_name         = "${var.name_prefix}-permissions-boundary"
  boundary_policy_arn   = "${local.iam_prefix}:policy${local.role_path}${local.boundary_name}"
  github_oidc_condition = "token.actions.githubusercontent.com"
  github_allowed_events = ["schedule", "workflow_dispatch"]
  github_oidc_subject_template_keys = [
    "repo",
    "context",
    "job_workflow_ref",
    "event_name",
  ]
  github_oidc_subjects = [
    for event_name in local.github_allowed_events :
    "${var.github_oidc_repository_subject}:environment:${var.github_environment}:job_workflow_ref:${var.github_workflow_ref}:event_name:${event_name}"
  ]

  common_tags = {
    PortfolioManaged    = "true"
    PortfolioRepository = var.repository_identity
    PortfolioLayer      = "bootstrap"
    PortfolioPersistent = "true"
  }

  ecr_repositories = {
    web = "${var.name_prefix}/web"
    api = "${var.name_prefix}/api"
    ml  = "${var.name_prefix}/ml"
  }
  ecr_repository_arns = {
    for purpose, name in local.ecr_repositories :
    purpose => "arn:${var.aws_partition}:ecr:${var.aws_region}:${var.aws_account_id}:repository/${name}"
  }

  global_role_names = {
    iam_manager = "${var.name_prefix}-iam-manager"
    automation  = "${var.name_prefix}-automation"
  }
  global_role_arns = {
    for purpose, name in local.global_role_names :
    purpose => "${local.iam_prefix}:role${local.role_path}${name}"
  }

  environment_role_purposes = toset([
    "operator-deployment",
    "task-execution",
    "web-workload",
    "api-workload",
    "ml-workload",
    "scheduler",
    "codebuild-image",
    "codebuild-destroy",
    "destroy",
  ])
  environment_roles = merge([
    for environment in sort(keys(var.environment_state_keys)) : {
      for purpose in local.environment_role_purposes :
      "${environment}/${purpose}" => {
        environment = environment
        purpose     = purpose
        name        = "${var.name_prefix}-${environment}-${purpose}"
      }
    }
  ]...)
  environment_role_arns = {
    for key, role in local.environment_roles :
    key => "${local.iam_prefix}:role${local.role_path}${role.name}"
  }

  environment_state_arns = {
    for environment, key in var.environment_state_keys :
    environment => "${local.state_bucket_arn}/${key}"
  }
  environment_lock_arns = {
    for environment, arn in local.environment_state_arns :
    environment => "${arn}.tflock"
  }
  environment_app_bucket_arns = {
    for environment in keys(var.environment_state_keys) :
    environment => "arn:${var.aws_partition}:s3:::${var.name_prefix}-${environment}-documents"
  }

  ecs_service_principal       = "ecs-tasks.amazonaws.com"
  scheduler_service_principal = "scheduler.amazonaws.com"
  codebuild_service_principal = "codebuild.amazonaws.com"

  human_trust_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "ExactOwnerPrincipal"
      Effect    = "Allow"
      Principal = { AWS = var.owner_principal_arn }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "aws:PrincipalAccount" = var.aws_account_id }
      }
    }]
  })

  automation_trust_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "ExactGitHubDeploymentWorkflow"
      Effect    = "Allow"
      Principal = { Federated = var.github_oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${local.github_oidc_condition}:aud"              = "sts.amazonaws.com"
          "${local.github_oidc_condition}:sub"              = local.github_oidc_subjects
          "${local.github_oidc_condition}:repository"       = var.repository_identity
          "${local.github_oidc_condition}:ref"              = "refs/heads/main"
          "${local.github_oidc_condition}:environment"      = var.github_environment
          "${local.github_oidc_condition}:job_workflow_ref" = var.github_workflow_ref
          "${local.github_oidc_condition}:workflow"         = var.github_workflow_name
        }
      }
    }]
  })

  ecs_trust_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "ExactAccountEcsTasks"
      Effect    = "Allow"
      Principal = { Service = local.ecs_service_principal }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "aws:SourceAccount" = var.aws_account_id }
        ArnLike      = { "aws:SourceArn" = "arn:${var.aws_partition}:ecs:${var.aws_region}:${var.aws_account_id}:*" }
      }
    }]
  })

  scheduler_trust_policies = {
    for environment in keys(var.environment_state_keys) : environment => jsonencode({
      Version = "2012-10-17"
      Statement = [{
        Sid       = "ExactEnvironmentScheduleGroup"
        Effect    = "Allow"
        Principal = { Service = local.scheduler_service_principal }
        Action    = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = var.aws_account_id
            "aws:SourceArn"     = "arn:${var.aws_partition}:scheduler:${var.aws_region}:${var.aws_account_id}:schedule-group/${var.name_prefix}-${environment}-lifecycle"
          }
        }
      }]
    })
  }

  codebuild_trust_policies = {
    for environment in keys(var.environment_state_keys) : environment => jsonencode({
      Version = "2012-10-17"
      Statement = [{
        Sid       = "ExactEnvironmentDestroyProject"
        Effect    = "Allow"
        Principal = { Service = local.codebuild_service_principal }
        Action    = "sts:AssumeRole"
        Condition = {
          StringEquals = { "aws:SourceAccount" = var.aws_account_id }
          ArnLike      = { "aws:SourceArn" = "arn:${var.aws_partition}:codebuild:${var.aws_region}:${var.aws_account_id}:project/${var.name_prefix}-${environment}-destroy" }
        }
      }]
    })
  }

  codebuild_image_trust_policies = {
    for environment in keys(var.environment_state_keys) : environment => jsonencode({
      Version = "2012-10-17"
      Statement = [{
        Sid       = "ExactEnvironmentImageProject"
        Effect    = "Allow"
        Principal = { Service = local.codebuild_service_principal }
        Action    = "sts:AssumeRole"
        Condition = {
          StringEquals = { "aws:SourceAccount" = var.aws_account_id }
          ArnLike      = { "aws:SourceArn" = "arn:${var.aws_partition}:codebuild:${var.aws_region}:${var.aws_account_id}:project/${var.name_prefix}-${environment}-image-build" }
        }
      }]
    })
  }

  destroy_trust_policies = {
    for environment in keys(var.environment_state_keys) : environment => jsonencode({
      Version = "2012-10-17"
      Statement = [{
        Sid    = "ExactDestroyControllers"
        Effect = "Allow"
        Principal = {
          AWS = [
            local.global_role_arns.automation,
            local.environment_role_arns["${environment}/codebuild-destroy"],
          ]
        }
        Action = "sts:AssumeRole"
      }]
    })
  }

  environment_assume_role_policies = {
    for key, role in local.environment_roles : key => (
      role.purpose == "operator-deployment" ? local.human_trust_policy :
      contains(["task-execution", "web-workload", "api-workload", "ml-workload"], role.purpose) ? local.ecs_trust_policy :
      role.purpose == "scheduler" ? local.scheduler_trust_policies[role.environment] :
      role.purpose == "codebuild-image" ? local.codebuild_image_trust_policies[role.environment] :
      role.purpose == "codebuild-destroy" ? local.codebuild_trust_policies[role.environment] :
      local.destroy_trust_policies[role.environment]
    )
  }
}
