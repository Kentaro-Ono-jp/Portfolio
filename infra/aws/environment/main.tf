module "network" {
  source = "./modules/network"

  name                          = local.name
  aws_region                    = var.aws_region
  availability_zones            = var.availability_zones
  vpc_cidr                      = var.vpc_cidr
  public_task_subnet_cidrs      = var.public_task_subnet_cidrs
  isolated_service_subnet_cidrs = var.isolated_service_subnet_cidrs
}

module "ingress" {
  source = "./modules/ingress"

  name                       = local.name
  vpc_id                     = module.network.vpc_id
  public_task_subnet_ids     = module.network.public_task_subnet_ids
  vpc_link_security_group_id = module.network.security_group_ids.vpc_link
  log_path_prefix            = "/portfolio/${var.name_prefix}/${var.environment}"
  log_retention_days         = var.log_retention_days
}

module "identity" {
  source = "./modules/identity"

  name                = local.name
  aws_account_id      = var.aws_account_id
  aws_partition       = var.aws_partition
  aws_region          = var.aws_region
  public_web_base_url = module.ingress.public_api_endpoint
  reviewer_group_name = var.reviewer_group_name
  oidc_api_audience   = var.oidc_api_audience
}

module "managed_state" {
  source = "./modules/managed-state"

  name                        = local.name
  aws_partition               = var.aws_partition
  aws_region                  = var.aws_region
  isolated_service_subnet_ids = module.network.isolated_service_subnet_ids
  database_security_group_id  = module.network.security_group_ids.database
  broker_security_group_id    = module.network.security_group_ids.broker
  rds_instance_class          = var.rds_instance_class
  mq_instance_type            = var.mq_instance_type
  object_expiration_days      = var.object_expiration_days
}

module "runtime" {
  source = "./modules/runtime"

  name                    = local.name
  aws_region              = var.aws_region
  public_task_subnet_ids  = module.network.public_task_subnet_ids
  security_group_ids      = module.network.security_group_ids
  cloud_map               = module.ingress.cloud_map
  api_base_url            = module.ingress.api_endpoint
  public_web_base_url     = module.ingress.public_api_endpoint
  identity                = module.identity.runtime_contract
  application_bucket_name = module.managed_state.application_bucket_name
  runtime_secret_arns     = module.managed_state.runtime_secret_arns
  image_references        = local.image_references
  runtime_sizing          = local.runtime_sizing
  task_execution_role_arn = var.bootstrap_role_arns.task_execution
  workload_role_arns = {
    web = var.bootstrap_role_arns.web_workload
    api = var.bootstrap_role_arns.api_workload
    ml  = var.bootstrap_role_arns.ml_workload
  }
  log_path_prefix    = "/portfolio/${var.name_prefix}/${var.environment}"
  log_retention_days = var.log_retention_days

  depends_on = [module.managed_state]
}
