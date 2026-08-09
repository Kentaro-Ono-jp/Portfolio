variable "aws_account_id" {
  description = "Twelve-digit AWS account that will own every bootstrap resource and cost."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must be exactly twelve decimal digits."
  }
}

variable "aws_partition" {
  description = "AWS partition for generated ARNs."
  type        = string

  validation {
    condition     = contains(["aws", "aws-us-gov", "aws-cn"], var.aws_partition)
    error_message = "aws_partition must be aws, aws-us-gov, or aws-cn."
  }
}

variable "aws_region" {
  description = "AWS region that owns the state bucket, ECR repositories, and later environments."
  type        = string

  validation {
    condition = (
      can(regex("^[a-z]{2}(?:-gov)?-[a-z]+-[0-9]+$", var.aws_region)) &&
      (var.aws_partition == "aws-cn") == startswith(var.aws_region, "cn-") &&
      (var.aws_partition == "aws-us-gov") == startswith(var.aws_region, "us-gov-")
    )
    error_message = "aws_region must be explicit and consistent with aws_partition."
  }
}

variable "name_prefix" {
  description = "Portable lowercase prefix used for every owned name and IAM path."
  type        = string

  validation {
    condition = (
      can(regex("^[a-z][a-z0-9-]{1,18}[a-z0-9]$", var.name_prefix)) &&
      !strcontains(var.name_prefix, "--")
    )
    error_message = "name_prefix must be 3-20 lowercase alphanumeric or hyphen characters, start with a letter, end alphanumeric, and contain no consecutive hyphens."
  }
}

variable "repository_identity" {
  description = "GitHub repository in owner/name form; also becomes a required ownership tag."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.repository_identity))
    error_message = "repository_identity must be an explicit owner/name pair."
  }
}

variable "state_bucket_name" {
  description = "Globally unique S3 bucket name chosen by the account owner."
  type        = string

  validation {
    condition = (
      length(var.state_bucket_name) >= 3 &&
      length(var.state_bucket_name) <= 63 &&
      can(regex("^[a-z0-9][a-z0-9.-]*[a-z0-9]$", var.state_bucket_name)) &&
      !can(regex("\\.\\.", var.state_bucket_name)) &&
      !can(regex("^[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+$", var.state_bucket_name)) &&
      startswith(var.state_bucket_name, "${var.name_prefix}-")
    )
    error_message = "state_bucket_name must be an explicit valid 3-63 character S3 bucket name under name_prefix."
  }
}

variable "bootstrap_state_key" {
  description = "Dedicated object key to which the initial local bootstrap state is migrated."
  type        = string

  validation {
    condition     = can(regex("^bootstrap/[a-z0-9][a-z0-9/_-]*\\.tfstate$", var.bootstrap_state_key))
    error_message = "bootstrap_state_key must be a bootstrap/...tfstate key."
  }
}

variable "environment_state_keys" {
  description = "Exact later-environment name to isolated S3 state-key mapping."
  type        = map(string)

  validation {
    condition = (
      length(var.environment_state_keys) > 0 &&
      alltrue([
        for environment, key in var.environment_state_keys :
        can(regex("^[a-z][a-z0-9-]{0,14}[a-z0-9]$", environment)) &&
        !strcontains(environment, "--") &&
        key == "environments/${environment}/terraform.tfstate"
      ]) &&
      length(distinct(values(var.environment_state_keys))) == length(var.environment_state_keys)
    )
    error_message = "Each environment must be a portable 2-16 character name without trailing/consecutive hyphens, use the exact key environments/<name>/terraform.tfstate, and have a unique key."
  }
}

variable "owner_principal_arn" {
  description = "Existing third-party-owned IAM user or role ARN allowed to assume the human bootstrap roles."
  type        = string

  validation {
    condition = can(regex(
      "^arn:${var.aws_partition}:iam::${var.aws_account_id}:(user|role)/[A-Za-z0-9+=,.@_/-]+$",
      var.owner_principal_arn,
    ))
    error_message = "owner_principal_arn must be an explicit IAM user or role ARN in aws_account_id and aws_partition."
  }
}

variable "github_oidc_provider_arn" {
  description = "Existing GitHub Actions OIDC provider ARN owned by the target account."
  type        = string

  validation {
    condition = var.github_oidc_provider_arn == (
      "arn:${var.aws_partition}:iam::${var.aws_account_id}:oidc-provider/token.actions.githubusercontent.com"
    )
    error_message = "github_oidc_provider_arn must name this account's token.actions.githubusercontent.com provider."
  }
}

variable "github_oidc_repository_subject" {
  description = "Explicit repo subject segment used by the customized GitHub OIDC sub claim; immutable repositories include owner and repository IDs."
  type        = string

  validation {
    condition = can(regex(
      "^repo:[A-Za-z0-9_.-]+(?:@[0-9]+)?/[A-Za-z0-9_.-]+(?:@[0-9]+)?$",
      var.github_oidc_repository_subject,
    ))
    error_message = "github_oidc_repository_subject must be repo:<owner>/<repository> or the immutable repo:<owner>@<id>/<repository>@<id> form."
  }
}

variable "github_environment" {
  description = "Protected GitHub environment required by the future deployment workflow."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]{2,64}$", var.github_environment))
    error_message = "github_environment must be an explicit protected-environment name."
  }
}

variable "github_workflow_ref" {
  description = "Exact reusable deployment workflow identity, including @refs/heads/main."
  type        = string

  validation {
    condition = (
      can(regex(
        "^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/\\.github/workflows/[A-Za-z0-9_.-]+\\.ya?ml@refs/heads/main$",
        var.github_workflow_ref,
      )) &&
      startswith(var.github_workflow_ref, "${var.repository_identity}/.github/workflows/")
    )
    error_message = "github_workflow_ref must identify an exact repository workflow at refs/heads/main."
  }
}

variable "github_workflow_name" {
  description = "Exact future deployment workflow display name used in OIDC trust."
  type        = string

  validation {
    condition     = length(trimspace(var.github_workflow_name)) >= 3
    error_message = "github_workflow_name must be explicit."
  }
}
