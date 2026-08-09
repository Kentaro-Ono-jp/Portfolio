output "ecs_cluster_name" {
  value = aws_ecs_cluster.environment.name
}

output "ecs_service_names" {
  value = {
    web = aws_ecs_service.application["web"].name
    api = aws_ecs_service.application["api"].name
    ml  = aws_ecs_service.ml.name
  }
}

output "migration_task_definition_arn" {
  value = aws_ecs_task_definition.migration.arn
}

output "static_contract" {
  value = {
    network_mode         = "awsvpc"
    launch_type          = "FARGATE"
    platform_version     = "1.4.0"
    public_task_subnets  = 2
    public_ip_assignment = true
    task_count           = 3
    service_count        = 3
    migration_is_service = false
    execution_role_arn   = var.task_execution_role_arn
    tasks = {
      web = {
        cpu           = var.runtime_sizing.tasks.web.cpuUnits
        memory        = var.runtime_sizing.tasks.web.memoryMiB
        image         = var.image_references.web
        workload_role = var.workload_role_arns.web
        containers    = ["web"]
        secret_names  = []
      }
      api = {
        cpu           = var.runtime_sizing.tasks["api-area"].cpuUnits
        memory        = var.runtime_sizing.tasks["api-area"].memoryMiB
        image         = var.image_references.api
        workload_role = var.workload_role_arns.api
        containers    = ["api", "outbox-publisher", "result-consumer"]
        secret_names  = ["PORTFOLIO_DATABASE_URL", "PORTFOLIO_RABBITMQ_URL"]
      }
      ml = {
        cpu               = var.runtime_sizing.tasks.ml.cpuUnits
        memory            = var.runtime_sizing.tasks.ml.memoryMiB
        image             = var.image_references.ml
        workload_role     = var.workload_role_arns.ml
        containers        = ["ml-worker"]
        secret_names      = ["PORTFOLIO_ML_RABBITMQ_URL"]
        database_secret   = false
        end_user_identity = false
      }
    }
    migration = {
      image         = var.image_references.api
      workload_role = var.workload_role_arns.api
      executed      = false
    }
    web_application_store_credentials = false
    log_group_count                   = 4
    log_retention_days                = var.log_retention_days
  }
}
