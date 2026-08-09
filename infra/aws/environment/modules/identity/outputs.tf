output "runtime_contract" {
  value = {
    issuer            = local.issuer
    authorization_url = "${local.authorization_origin}/oauth2/authorize"
    discovery_url     = "${local.issuer}/.well-known/openid-configuration"
    token_url         = "${local.authorization_origin}/oauth2/token"
    jwks_url          = "${local.issuer}/.well-known/jwks.json"
    client_id         = aws_cognito_user_pool_client.web.id
    scopes            = join(" ", ["openid", local.api_scope])
    audience          = var.oidc_api_audience
    capability_claim  = "cognito:groups"
    reviewer_group    = var.reviewer_group_name
  }
}

output "user_pool_id" {
  value = aws_cognito_user_pool.environment.id
}

output "client_id" {
  value = aws_cognito_user_pool_client.web.id
}

output "static_contract" {
  value = {
    public_client           = true
    client_secret_generated = false
    authorization_code_flow = true
    pkce_required           = true
    managed_login_version   = 2
    public_signup           = false
    seeded_users            = 0
    access_token_audience   = var.oidc_api_audience
    capability_claim        = "cognito:groups"
    accepted_group          = var.reviewer_group_name
  }
}
