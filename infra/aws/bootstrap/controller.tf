locals {
  controller_projects = merge([
    for environment in sort(keys(var.environment_state_keys)) : {
      for purpose in ["image", "destroy"] :
      "${environment}/${purpose}" => {
        environment = environment
        purpose     = purpose
        name = (
          purpose == "image"
          ? "${var.name_prefix}-${environment}-image-build"
          : "${var.name_prefix}-${environment}-destroy"
        )
        role_key = (
          purpose == "image"
          ? "${environment}/codebuild-image"
          : "${environment}/codebuild-destroy"
        )
        buildspec = (
          purpose == "image"
          ? "${path.module}/../lifecycle/image-build.buildspec.yml"
          : "${path.module}/../lifecycle/destroy.buildspec.yml"
        )
      }
    }
  ]...)
}

resource "aws_cloudwatch_log_group" "controller" {
  for_each = local.controller_projects

  name              = "/portfolio/${var.name_prefix}/${each.value.environment}/controller/${each.value.purpose}"
  retention_in_days = 7

  tags = {
    PortfolioEnvironment = each.value.environment
    PortfolioPurpose     = "${each.value.purpose}-controller"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_codebuild_project" "controller" {
  for_each = local.controller_projects

  name             = each.value.name
  description      = "Persistent Portfolio ${each.value.purpose} controller for ${each.value.environment}."
  service_role     = aws_iam_role.environment[each.value.role_key].arn
  build_timeout    = 60
  queued_timeout   = 30
  auto_retry_limit = each.value.purpose == "destroy" ? 2 : 0

  artifacts {
    type = "NO_ARTIFACTS"
  }

  environment {
    compute_type                = "BUILD_GENERAL1_SMALL"
    image                       = "aws/codebuild/standard:7.0"
    type                        = "LINUX_CONTAINER"
    image_pull_credentials_type = "CODEBUILD"
    privileged_mode             = each.value.purpose == "image"

    environment_variable {
      name  = "PORTFOLIO_STATE_BUCKET"
      value = var.state_bucket_name
    }
    environment_variable {
      name  = "PORTFOLIO_CONFIGURATION_KEY"
      value = "controls/${var.name_prefix}/${each.value.environment}/configuration.json"
    }
    environment_variable {
      name  = "PORTFOLIO_DESTROY_ROLE_ARN"
      value = local.environment_role_arns["${each.value.environment}/destroy"]
    }
    environment_variable {
      name  = "PORTFOLIO_AWS_REGION"
      value = var.aws_region
    }
  }

  logs_config {
    cloudwatch_logs {
      group_name  = aws_cloudwatch_log_group.controller[each.key].name
      stream_name = each.value.purpose
      status      = "ENABLED"
    }
  }

  source {
    type      = "NO_SOURCE"
    buildspec = file(each.value.buildspec)
  }

  tags = {
    PortfolioEnvironment = each.value.environment
    PortfolioPurpose     = "${each.value.purpose}-controller"
  }

  lifecycle {
    prevent_destroy = true
  }
}
