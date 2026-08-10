output "ownership_contract" {
  description = "Deterministic state and tag boundary used by later lifecycle operations."
  value = {
    environment_state_key = var.environment_state_key
    tags                  = local.ownership_tags
  }
}

output "public_endpoints" {
  description = "Non-secret generated endpoints and private service identifiers required by Step 5."
  value = {
    web_https             = module.ingress.public_api_endpoint
    api_https             = module.ingress.api_endpoint
    api_private_dns       = module.ingress.cloud_map.api_dns_name
    cognito_authorization = module.identity.runtime_contract.authorization_url
    cognito_issuer        = module.identity.runtime_contract.issuer
    database              = module.managed_state.database_endpoint
    broker                = module.managed_state.broker_endpoints
  }
}

output "service_identifiers" {
  description = "Deterministic identifiers for ECS, Cloud Map, Cognito, S3, and the migration task."
  value = {
    ecs_cluster               = module.runtime.ecs_cluster_name
    ecs_services              = module.runtime.ecs_service_names
    migration_task_definition = module.runtime.migration_task_definition_arn
    cloud_map_namespace       = module.ingress.cloud_map.namespace_name
    cognito_user_pool_id      = module.identity.user_pool_id
    cognito_client_id         = module.identity.client_id
    application_bucket        = module.managed_state.application_bucket_name
  }
}

output "migration_network" {
  description = "Exact Fargate network boundary for the one-shot API-area migration task."
  value = {
    subnet_ids        = module.network.public_task_subnet_ids
    security_group_id = module.network.security_group_ids.api
    public_ip         = true
  }
}

output "bootstrap_references" {
  description = "Persistent resources consumed by ARN/URL reference only and never owned by this state."
  value = {
    role_arns        = var.bootstrap_role_arns
    repository_urls  = var.ecr_repository_urls
    image_references = local.image_references
  }
}

output "secret_references" {
  description = "Execution-time secret references; secret values are never outputs."
  value       = module.managed_state.runtime_secret_arns
  sensitive   = true
}

output "static_contract" {
  description = "AWS-free deterministic topology contract cross-checked against the sanitized plan."
  value = {
    ownership = {
      state_key = var.environment_state_key
      tags      = local.ownership_tags
    }
    network  = module.network.static_contract
    ingress  = module.ingress.static_contract
    identity = module.identity.static_contract
    state    = module.managed_state.static_contract
    runtime  = module.runtime.static_contract
  }
}
