resource "aws_iam_policy" "permissions_boundary" {
  name        = local.boundary_name
  path        = local.role_path
  description = "Maximum portable authority for Portfolio bootstrap roles."
  policy      = local.permissions_boundary_policy

  lifecycle {
    prevent_destroy = true
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
  }
}

resource "aws_iam_role_policy" "global" {
  for_each = local.global_identity_policies

  name   = "${var.name_prefix}-${replace(each.key, "_", "-")}-authority"
  role   = aws_iam_role.global[each.key].name
  policy = each.value
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
  }
}

resource "aws_iam_role_policy" "environment" {
  for_each = local.environment_identity_policies

  name   = "${var.name_prefix}-${replace(each.key, "/", "-")}-authority"
  role   = aws_iam_role.environment[each.key].name
  policy = each.value
}
