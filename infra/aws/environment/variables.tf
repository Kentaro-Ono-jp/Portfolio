variable "aws_account_id" {
  description = "Twelve-digit account that will own the ephemeral environment and its cost."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must be exactly twelve decimal digits."
  }
}

variable "aws_partition" {
  description = "AWS partition used to construct and validate every persistent reference."
  type        = string

  validation {
    condition     = contains(["aws", "aws-us-gov", "aws-cn"], var.aws_partition)
    error_message = "aws_partition must be aws, aws-us-gov, or aws-cn."
  }
}

variable "aws_region" {
  description = "Explicit region for every environment resource."
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

variable "availability_zones" {
  description = "Exactly two explicit availability zones in aws_region; no AWS discovery is performed."
  type        = list(string)

  validation {
    condition = (
      length(var.availability_zones) == 2 &&
      length(distinct(var.availability_zones)) == 2 &&
      alltrue([
        for zone in var.availability_zones :
        can(regex("^${var.aws_region}[a-z]$", zone))
      ])
    )
    error_message = "availability_zones must contain two distinct zones belonging to aws_region."
  }
}

variable "name_prefix" {
  description = "Portable lowercase prefix shared with the persistent bootstrap."
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
  description = "Public GitHub repository in owner/name form and the exact ownership tag value."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.repository_identity))
    error_message = "repository_identity must be an explicit owner/name pair."
  }
}

variable "environment" {
  description = "Short isolated environment name shared with bootstrap roles and state."
  type        = string

  validation {
    condition = (
      can(regex("^[a-z][a-z0-9-]{0,14}[a-z0-9]$", var.environment)) &&
      !strcontains(var.environment, "--")
    )
    error_message = "environment must be 2-16 lowercase alphanumeric or hyphen characters, end alphanumeric, and contain no consecutive hyphens."
  }
}

variable "environment_state_key" {
  description = "The one exact backend key that owns every resource in this root."
  type        = string

  validation {
    condition     = var.environment_state_key == "environments/${var.environment}/terraform.tfstate"
    error_message = "environment_state_key must be exactly environments/<environment>/terraform.tfstate."
  }
}

variable "bootstrap_role_arns" {
  description = "Persistent bootstrap- or Console-owned role ARNs consumed by reference only; this root never owns IAM roles."
  type = object({
    operator_deployment = string
    task_execution      = string
    web_workload        = string
    api_workload        = string
    ml_workload         = string
    destroy             = string
  })

  validation {
    condition = alltrue([
      for purpose, arn in var.bootstrap_role_arns : contains(
        [
          format(
            "arn:%s:iam::%s:role/%s/%s-%s-%s",
            var.aws_partition,
            var.aws_account_id,
            var.name_prefix,
            var.name_prefix,
            var.environment,
            replace(purpose, "_", "-"),
          ),
          format(
            "arn:%s:iam::%s:role/%s-%s-%s",
            var.aws_partition,
            var.aws_account_id,
            var.name_prefix,
            var.environment,
            replace(purpose, "_", "-"),
          ),
        ],
        arn,
      )
    ])
    error_message = "Every role ARN must be the exact account/partition/prefix/environment purpose role, either under the bootstrap IAM path or as the Console-owned root role."
  }
}

variable "ecr_repository_urls" {
  description = "Persistent immutable ECR repository outputs for the three deployable areas."
  type = object({
    web = string
    api = string
    ml  = string
  })

  validation {
    condition = alltrue([
      for purpose, url in var.ecr_repository_urls : url == format(
        "%s.dkr.ecr.%s.%s/%s/%s",
        var.aws_account_id,
        var.aws_region,
        var.aws_partition == "aws-cn" ? "amazonaws.com.cn" : "amazonaws.com",
        var.name_prefix,
        purpose,
      )
    ])
    error_message = "Every ECR URL must be the exact account/region/prefix repository emitted by bootstrap."
  }
}

variable "image_digests" {
  description = "Immutable Web/API/ML image digests; mutable tags are not accepted."
  type = object({
    web = string
    api = string
    ml  = string
  })

  validation {
    condition     = alltrue([for digest in values(var.image_digests) : can(regex("^sha256:[0-9a-f]{64}$", digest))])
    error_message = "Every image digest must be a lowercase sha256 digest."
  }
}

variable "vpc_cidr" {
  description = "Explicit VPC CIDR for this environment."
  type        = string

  validation {
    condition = (
      can(cidrhost(var.vpc_cidr, 2)) &&
      can(regex("/16$", var.vpc_cidr)) &&
      var.vpc_cidr == "${try(cidrhost(var.vpc_cidr, 0), "invalid")}/16"
    )
    error_message = "vpc_cidr must be a canonical IPv4 /16 network with room for the accepted subnet layout."
  }
}

variable "public_task_subnet_cidrs" {
  description = "Two public task subnet CIDRs aligned by index with availability_zones."
  type        = list(string)

  validation {
    condition = var.public_task_subnet_cidrs == tolist([
      cidrsubnet(var.vpc_cidr, 8, 0),
      cidrsubnet(var.vpc_cidr, 8, 1),
    ])
    error_message = "public_task_subnet_cidrs must be the first two /24 subnets derived from vpc_cidr."
  }
}

variable "isolated_service_subnet_cidrs" {
  description = "Two isolated RDS/MQ subnet CIDRs aligned by index with availability_zones."
  type        = list(string)

  validation {
    condition = var.isolated_service_subnet_cidrs == tolist([
      cidrsubnet(var.vpc_cidr, 8, 10),
      cidrsubnet(var.vpc_cidr, 8, 11),
    ])
    error_message = "isolated_service_subnet_cidrs must be the accepted isolated /24 subnets 10 and 11 derived from vpc_cidr."
  }
}

variable "rds_instance_class" {
  description = "Evaluation-sized PostgreSQL instance class."
  type        = string

  validation {
    condition     = contains(["db.t4g.micro", "db.t4g.small"], var.rds_instance_class)
    error_message = "rds_instance_class must remain within the accepted evaluation-sized t4g set."
  }
}

variable "mq_instance_type" {
  description = "RabbitMQ 4.2 compatible evaluation broker instance type."
  type        = string

  validation {
    condition     = var.mq_instance_type == "mq.m7g.large"
    error_message = "RabbitMQ 4.2 currently requires the accepted mq.m7g.large evaluation type."
  }
}

variable "log_retention_days" {
  description = "Bounded retention for environment-owned CloudWatch log groups."
  type        = number

  validation {
    condition     = contains([1, 3, 5, 7, 14], var.log_retention_days)
    error_message = "log_retention_days must be one of the accepted short-lived CloudWatch retention periods."
  }
}

variable "object_expiration_days" {
  description = "Bounded lifetime for synthetic application objects."
  type        = number

  validation {
    condition     = var.object_expiration_days >= 1 && var.object_expiration_days <= 7
    error_message = "object_expiration_days must remain between one and seven days."
  }
}

variable "reviewer_group_name" {
  description = "Cognito group mapped to the accepted review capability boundary."
  type        = string

  validation {
    condition     = var.reviewer_group_name == "reactorfront-reviewers"
    error_message = "reviewer_group_name must preserve the accepted reactorfront-reviewers boundary."
  }
}

variable "oidc_api_audience" {
  description = "Stable resource-server identifier required in Cognito access tokens."
  type        = string

  validation {
    condition     = can(regex("^https://[a-z0-9.-]+/api$", var.oidc_api_audience))
    error_message = "oidc_api_audience must be a stable HTTPS API resource identifier."
  }
}
