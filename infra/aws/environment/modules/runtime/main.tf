locals {
  log_groups = {
    web       = "${var.log_path_prefix}/web"
    api       = "${var.log_path_prefix}/api"
    ml        = "${var.log_path_prefix}/ml"
    migration = "${var.log_path_prefix}/migration"
  }

  log_configuration = {
    for name, log_group in aws_cloudwatch_log_group.runtime : name => {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = log_group.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = name
      }
    }
  }

  database_secret = [{
    name      = "PORTFOLIO_DATABASE_URL"
    valueFrom = "${var.runtime_secret_arns.database}:database_url::"
  }]
  broker_secret = [{
    name      = "PORTFOLIO_RABBITMQ_URL"
    valueFrom = "${var.runtime_secret_arns.broker}:broker_url::"
  }]
  ml_broker_secret = [{
    name      = "PORTFOLIO_ML_RABBITMQ_URL"
    valueFrom = "${var.runtime_secret_arns.broker}:broker_url::"
  }]

  api_environment = {
    PORTFOLIO_EVENT_CONTRACT_DIRECTORY = "/workspace/packages/contracts/events"
    PORTFOLIO_OIDC_ALLOWED_ALGORITHM   = "RS256"
    PORTFOLIO_OIDC_AUDIENCE            = var.identity.audience
    PORTFOLIO_OIDC_CAPABILITY_CLAIM    = var.identity.capability_claim
    PORTFOLIO_OIDC_CAPABILITY_MAPPING = jsonencode({
      (var.identity.reviewer_group) = ["documents:submit", "documents:read", "reviews:write", "audit:read"]
    })
    PORTFOLIO_OIDC_DISCOVERY_URL = var.identity.discovery_url
    PORTFOLIO_OIDC_ISSUER        = var.identity.issuer
    PORTFOLIO_OIDC_JWKS_URL      = var.identity.jwks_url
    PORTFOLIO_OIDC_MODE          = "cognito"
    PORTFOLIO_S3_BUCKET          = var.application_bucket_name
    PORTFOLIO_S3_MODE            = "aws"
    PORTFOLIO_S3_REGION          = var.aws_region
  }
  outbox_environment = {
    PORTFOLIO_OUTBOX_BATCH_SIZE         = "8"
    PORTFOLIO_OUTBOX_LEASE_SECONDS      = "30"
    PORTFOLIO_OUTBOX_POLL_SECONDS       = "0.25"
    PORTFOLIO_OUTBOX_RETRY_BASE_SECONDS = "1"
    PORTFOLIO_OUTBOX_RETRY_MAX_SECONDS  = "30"
    PORTFOLIO_RABBITMQ_TIMEOUT_SECONDS  = "5"
  }
  events_environment = {
    PORTFOLIO_EVENTS_PREFETCH_COUNT          = "1"
    PORTFOLIO_EVENTS_RECONNECT_DELAY_SECONDS = "1"
    PORTFOLIO_EVENTS_REQUEUE_DELAY_SECONDS   = "0.25"
    PORTFOLIO_EVENT_CONTRACT_DIRECTORY       = "/workspace/packages/contracts/events"
    PORTFOLIO_RABBITMQ_TIMEOUT_SECONDS       = "5"
  }
  ml_environment = {
    PORTFOLIO_ML_EVALUATION_REPOSITORY_ROOT     = "/workspace"
    PORTFOLIO_ML_EVENT_CONTRACT_DIRECTORY       = "/workspace/packages/contracts/events"
    PORTFOLIO_ML_MODEL_ARTIFACT_PATH            = "/opt/reactorfront/model/model.json"
    PORTFOLIO_ML_MODEL_CHECKSUM_PATH            = "/opt/reactorfront/model/model.sha256"
    PORTFOLIO_ML_PROMOTION_MANIFEST_PATH        = "/workspace/apps/ml/evaluation/promoted-model-v1.json"
    PORTFOLIO_ML_PROMOTION_MANIFEST_SCHEMA_PATH = "/workspace/apps/ml/evaluation/promoted-model-v1.schema.json"
    PORTFOLIO_ML_RABBITMQ_TIMEOUT_SECONDS       = "5"
    PORTFOLIO_ML_S3_BUCKET                      = var.application_bucket_name
    PORTFOLIO_ML_S3_MODE                        = "aws"
    PORTFOLIO_ML_S3_REGION                      = var.aws_region
  }
  web_environment = {
    PORTFOLIO_API_BASE_URL                     = "http://${var.cloud_map.api_dns_name}:8000"
    PORTFOLIO_WEB_OIDC_ALLOW_INSECURE_LOOPBACK = "false"
    PORTFOLIO_WEB_OIDC_AUTHORIZATION_URL       = var.identity.authorization_url
    PORTFOLIO_WEB_OIDC_CLIENT_ID               = var.identity.client_id
    PORTFOLIO_WEB_OIDC_DISCOVERY_URL           = var.identity.discovery_url
    PORTFOLIO_WEB_OIDC_ISSUER                  = var.identity.issuer
    PORTFOLIO_WEB_OIDC_JWKS_URL                = var.identity.jwks_url
    PORTFOLIO_WEB_OIDC_SCOPES                  = var.identity.scopes
    PORTFOLIO_WEB_OIDC_TOKEN_URL               = var.identity.token_url
    PORTFOLIO_WEB_OIDC_TRANSACTION_SECONDS     = "300"
    PORTFOLIO_WEB_PUBLIC_BASE_URL              = var.public_web_base_url
    PORTFOLIO_WEB_SESSION_ABSOLUTE_SECONDS     = "3600"
    PORTFOLIO_WEB_SESSION_INACTIVITY_SECONDS   = "600"
    PORTFOLIO_WEB_TOKEN_REFRESH_LEEWAY_SECONDS = "30"
    PORTFOLIO_WEB_UPSTREAM_TIMEOUT_MS          = "8000"
  }

  api_containers = [
    {
      name                   = "api"
      image                  = var.image_references.api
      essential              = true
      cpu                    = 256
      memoryReservation      = var.runtime_sizing.processes.api.memoryCandidateMiB
      readonlyRootFilesystem = false
      portMappings = [{
        name          = "api"
        containerPort = 8000
        hostPort      = 8000
        protocol      = "tcp"
        appProtocol   = "http"
      }]
      environment      = [for name in sort(keys(local.api_environment)) : { name = name, value = local.api_environment[name] }]
      secrets          = local.database_secret
      logConfiguration = local.log_configuration.api
    },
    {
      name                   = "outbox-publisher"
      image                  = var.image_references.api
      essential              = true
      cpu                    = 128
      memoryReservation      = var.runtime_sizing.processes["api-outbox"].memoryCandidateMiB
      readonlyRootFilesystem = false
      command                = ["python", "-m", "reactorfront_api.outbox_main"]
      environment            = [for name in sort(keys(local.outbox_environment)) : { name = name, value = local.outbox_environment[name] }]
      secrets                = concat(local.database_secret, local.broker_secret)
      logConfiguration       = local.log_configuration.api
    },
    {
      name                   = "result-consumer"
      image                  = var.image_references.api
      essential              = true
      cpu                    = 128
      memoryReservation      = var.runtime_sizing.processes["api-events"].memoryCandidateMiB
      readonlyRootFilesystem = false
      command                = ["python", "-m", "reactorfront_api.events_main"]
      environment            = [for name in sort(keys(local.events_environment)) : { name = name, value = local.events_environment[name] }]
      secrets                = concat(local.database_secret, local.broker_secret)
      logConfiguration       = local.log_configuration.api
    },
  ]
}

resource "aws_cloudwatch_log_group" "runtime" {
  for_each = local.log_groups

  name              = each.value
  retention_in_days = var.log_retention_days
}

resource "aws_ecs_cluster" "environment" {
  name = var.name

  setting {
    name  = "containerInsights"
    value = "disabled"
  }
}

resource "aws_ecs_task_definition" "web" {
  family                   = "${var.name}-web"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = tostring(var.runtime_sizing.tasks.web.cpuUnits)
  memory                   = tostring(var.runtime_sizing.tasks.web.memoryMiB)
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.workload_role_arns.web
  container_definitions = jsonencode([{
    name                   = "web"
    image                  = var.image_references.web
    essential              = true
    cpu                    = var.runtime_sizing.tasks.web.cpuUnits
    memoryReservation      = var.runtime_sizing.processes.web.memoryCandidateMiB
    readonlyRootFilesystem = false
    portMappings = [{
      name          = "web"
      containerPort = 3000
      hostPort      = 3000
      protocol      = "tcp"
      appProtocol   = "http"
    }]
    environment      = [for name in sort(keys(local.web_environment)) : { name = name, value = local.web_environment[name] }]
    logConfiguration = local.log_configuration.web
  }])

  runtime_platform {
    cpu_architecture        = "X86_64"
    operating_system_family = "LINUX"
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.name}-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = tostring(var.runtime_sizing.tasks["api-area"].cpuUnits)
  memory                   = tostring(var.runtime_sizing.tasks["api-area"].memoryMiB)
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.workload_role_arns.api
  container_definitions    = jsonencode(local.api_containers)

  runtime_platform {
    cpu_architecture        = "X86_64"
    operating_system_family = "LINUX"
  }
}

resource "aws_ecs_task_definition" "migration" {
  family                   = "${var.name}-migration"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = tostring(var.runtime_sizing.tasks["api-area"].cpuUnits)
  memory                   = tostring(var.runtime_sizing.tasks["api-area"].memoryMiB)
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.workload_role_arns.api
  container_definitions = jsonencode([{
    name                   = "migration"
    image                  = var.image_references.api
    essential              = true
    cpu                    = var.runtime_sizing.tasks["api-area"].cpuUnits
    memoryReservation      = var.runtime_sizing.processes["api-migration"].memoryCandidateMiB
    readonlyRootFilesystem = false
    command                = ["alembic", "-c", "/workspace/apps/api/alembic.ini", "upgrade", "head"]
    secrets                = local.database_secret
    logConfiguration       = local.log_configuration.migration
  }])

  runtime_platform {
    cpu_architecture        = "X86_64"
    operating_system_family = "LINUX"
  }
}

resource "aws_ecs_task_definition" "ml" {
  family                   = "${var.name}-ml"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = tostring(var.runtime_sizing.tasks.ml.cpuUnits)
  memory                   = tostring(var.runtime_sizing.tasks.ml.memoryMiB)
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.workload_role_arns.ml
  container_definitions = jsonencode([{
    name                   = "ml-worker"
    image                  = var.image_references.ml
    essential              = true
    cpu                    = var.runtime_sizing.tasks.ml.cpuUnits
    memoryReservation      = var.runtime_sizing.processes["ml-worker"].memoryCandidateMiB
    readonlyRootFilesystem = false
    environment            = [for name in sort(keys(local.ml_environment)) : { name = name, value = local.ml_environment[name] }]
    secrets                = local.ml_broker_secret
    logConfiguration       = local.log_configuration.ml
  }])

  runtime_platform {
    cpu_architecture        = "X86_64"
    operating_system_family = "LINUX"
  }
}

resource "aws_ecs_service" "application" {
  for_each = {
    web = {
      task_definition = aws_ecs_task_definition.web.arn
      security_group  = var.security_group_ids.web
      registry_arn    = var.cloud_map.web_service_arn
      container_name  = "web"
      container_port  = 3000
    }
    api = {
      task_definition = aws_ecs_task_definition.api.arn
      security_group  = var.security_group_ids.api
      registry_arn    = var.cloud_map.api_service_arn
      container_name  = "api"
      container_port  = 8000
    }
  }

  name                               = "${var.name}-${each.key}"
  cluster                            = aws_ecs_cluster.environment.id
  task_definition                    = each.value.task_definition
  desired_count                      = 1
  launch_type                        = "FARGATE"
  platform_version                   = "1.4.0"
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100
  enable_execute_command             = false
  enable_ecs_managed_tags            = false
  propagate_tags                     = "TASK_DEFINITION"
  wait_for_steady_state              = false

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    assign_public_ip = true
    subnets          = var.public_task_subnet_ids
    security_groups  = [each.value.security_group]
  }

  service_registries {
    registry_arn   = each.value.registry_arn
    container_name = each.value.container_name
    container_port = each.value.container_port
  }
}

resource "aws_ecs_service" "ml" {
  name                               = "${var.name}-ml"
  cluster                            = aws_ecs_cluster.environment.id
  task_definition                    = aws_ecs_task_definition.ml.arn
  desired_count                      = 1
  launch_type                        = "FARGATE"
  platform_version                   = "1.4.0"
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100
  enable_execute_command             = false
  enable_ecs_managed_tags            = false
  propagate_tags                     = "TASK_DEFINITION"
  wait_for_steady_state              = false

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    assign_public_ip = true
    subnets          = var.public_task_subnet_ids
    security_groups  = [var.security_group_ids.ml]
  }
}
