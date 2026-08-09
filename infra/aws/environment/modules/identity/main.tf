locals {
  cognito_domain_suffix = var.aws_partition == "aws-cn" ? "amazoncognito.com.cn" : "amazoncognito.com"
  cognito_api_suffix    = var.aws_partition == "aws-cn" ? "amazonaws.com.cn" : "amazonaws.com"
  domain_prefix         = "${var.name}-${var.aws_account_id}"
  issuer                = "https://cognito-idp.${var.aws_region}.${local.cognito_api_suffix}/${aws_cognito_user_pool.environment.id}"
  authorization_origin  = "https://${aws_cognito_user_pool_domain.environment.domain}.auth.${var.aws_region}.${local.cognito_domain_suffix}"
  api_scope             = "${var.oidc_api_audience}/portfolio"
}

resource "aws_cognito_user_pool" "environment" {
  name                     = var.name
  deletion_protection      = "INACTIVE"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  mfa_configuration        = "OFF"

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 1
  }

  username_configuration {
    case_sensitive = false
  }
}

resource "aws_cognito_resource_server" "api" {
  identifier   = var.oidc_api_audience
  name         = "${var.name}-api"
  user_pool_id = aws_cognito_user_pool.environment.id

  scope {
    scope_name        = "portfolio"
    scope_description = "Submit and review repository-owned synthetic documents"
  }
}

resource "aws_cognito_user_pool_client" "web" {
  name                                 = "${var.name}-web"
  user_pool_id                         = aws_cognito_user_pool.environment.id
  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", local.api_scope]
  supported_identity_providers         = ["COGNITO"]
  callback_urls                        = ["${var.public_web_base_url}/api/auth/callback"]
  logout_urls                          = [var.public_web_base_url]
  prevent_user_existence_errors        = "ENABLED"
  enable_token_revocation              = true
  access_token_validity                = 1
  id_token_validity                    = 1
  refresh_token_validity               = 1
  explicit_auth_flows                  = ["ALLOW_REFRESH_TOKEN_AUTH"]

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }

  depends_on = [aws_cognito_resource_server.api]
}

resource "aws_cognito_user_pool_domain" "environment" {
  domain                = local.domain_prefix
  user_pool_id          = aws_cognito_user_pool.environment.id
  managed_login_version = 2
}

resource "aws_cognito_managed_login_branding" "web" {
  user_pool_id                = aws_cognito_user_pool.environment.id
  client_id                   = aws_cognito_user_pool_client.web.id
  use_cognito_provided_values = true

  depends_on = [aws_cognito_user_pool_domain.environment]
}

resource "aws_cognito_user_group" "reviewers" {
  name         = var.reviewer_group_name
  description  = "Accepted access-token capability group; Step 5 owns synthetic user seeding."
  precedence   = 0
  user_pool_id = aws_cognito_user_pool.environment.id
}
