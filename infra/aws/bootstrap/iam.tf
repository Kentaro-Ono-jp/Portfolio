resource "aws_iam_policy" "permissions_boundary" {
  name        = local.boundary_name
  path        = local.role_path
  description = "Maximum portable authority for Portfolio bootstrap roles."
  policy      = local.permissions_boundary_policy

  lifecycle {
    prevent_destroy = true

    precondition {
      condition     = length(local.permissions_boundary_policy) <= 5632
      error_message = "The permissions boundary must reserve at least 512 characters below the AWS 6,144-character managed-policy quota."
    }
  }
}

resource "aws_iam_role" "global" {
  for_each = local.global_role_names

  name                 = each.value
  path                 = local.role_path
  permissions_boundary = aws_iam_policy.permissions_boundary.arn
  assume_role_policy = (
    each.key == "automation" ? local.automation_trust_policy : local.human_trust_policy
  )

  tags = {
    PortfolioEnvironment = "shared"
    PortfolioPurpose     = replace(each.key, "_", "-")
  }

  lifecycle {
    prevent_destroy = true

    precondition {
      condition = length(
        each.key == "automation" ? local.automation_trust_policy : local.human_trust_policy
      ) <= 2048
      error_message = "A global role trust policy exceeds the portable 2,048-character default quota."
    }
  }
}

resource "aws_iam_role_policy" "global" {
  for_each = local.global_identity_policies

  name   = "${var.name_prefix}-${replace(each.key, "_", "-")}-authority"
  role   = aws_iam_role.global[each.key].name
  policy = each.value

  lifecycle {
    precondition {
      condition     = length(each.value) <= 9728
      error_message = "A global role inline policy must reserve at least 512 characters below the AWS 10,240-character aggregate role quota."
    }
  }
}

resource "aws_iam_role" "environment" {
  for_each = local.environment_roles

  name                 = each.value.name
  path                 = local.role_path
  permissions_boundary = aws_iam_policy.permissions_boundary.arn
  assume_role_policy   = local.environment_assume_role_policies[each.key]

  tags = {
    PortfolioEnvironment = each.value.environment
    PortfolioPurpose     = each.value.purpose
  }

  lifecycle {
    prevent_destroy = true

    precondition {
      condition     = length(local.environment_assume_role_policies[each.key]) <= 2048
      error_message = "An environment role trust policy exceeds the portable 2,048-character default quota."
    }
  }
}

resource "aws_iam_role_policy" "environment" {
  for_each = local.environment_inline_policies

  name   = "${var.name_prefix}-${replace(each.key, "/", "-")}-authority"
  role   = aws_iam_role.environment[each.key].name
  policy = each.value

  lifecycle {
    precondition {
      condition     = length(each.value) <= 9728
      error_message = "An environment role inline policy must reserve at least 512 characters below the AWS 10,240-character aggregate role quota."
    }
  }
}

resource "aws_iam_policy" "lifecycle_operator" {
  for_each = local.lifecycle_operator_policies

  name        = "${var.name_prefix}-${each.key}-lifecycle-control"
  path        = local.role_path
  description = "Persistent TTL lifecycle authority for ${each.key}."
  policy      = each.value

  lifecycle {
    prevent_destroy = true

    precondition {
      condition     = length(each.value) <= 5632
      error_message = "A lifecycle managed policy must preserve 512 characters of headroom."
    }
  }
}

resource "aws_iam_role_policy_attachment" "lifecycle_operator" {
  for_each = local.lifecycle_operator_policies

  role       = aws_iam_role.environment["${each.key}/operator-deployment"].name
  policy_arn = aws_iam_policy.lifecycle_operator[each.key].arn
}

resource "aws_iam_policy" "lifecycle_destroy" {
  for_each = local.lifecycle_destroy_policies

  name        = "${var.name_prefix}-${each.key}-lifecycle-destroy"
  path        = local.role_path
  description = "Persistent TTL destroy and residue authority for ${each.key}."
  policy      = each.value

  lifecycle {
    prevent_destroy = true

    precondition {
      condition     = length(each.value) <= 5632
      error_message = "A lifecycle destroy managed policy must preserve 512 characters of headroom."
    }
  }
}

resource "aws_iam_role_policy_attachment" "lifecycle_destroy" {
  for_each = local.lifecycle_destroy_policies

  role       = aws_iam_role.environment["${each.key}/destroy"].name
  policy_arn = aws_iam_policy.lifecycle_destroy[each.key].arn
}
