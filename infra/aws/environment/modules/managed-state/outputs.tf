output "application_bucket_name" {
  value = aws_s3_bucket.application.bucket
}

output "runtime_secret_arns" {
  value = {
    database = aws_secretsmanager_secret.database.arn
    broker   = aws_secretsmanager_secret.broker.arn
  }
}

output "database_endpoint" {
  value = aws_db_instance.postgresql.endpoint
}

output "broker_endpoints" {
  value = aws_mq_broker.rabbitmq.instances[0].endpoints
}

output "static_contract" {
  value = {
    postgresql = {
      engine                = "postgres"
      engine_version        = "18"
      instance_class        = var.rds_instance_class
      allocated_storage_gib = 20
      single_az             = true
      encrypted             = true
      publicly_accessible   = false
      isolated_subnet_count = 2
      deletion_protection   = false
      final_snapshot        = false
      automated_backup_days = 0
    }
    object_store = {
      encrypted                  = true
      public_access_blocked      = true
      force_destroy              = true
      expiration_days            = var.object_expiration_days
      abort_multipart_after_days = 1
    }
    rabbitmq = {
      engine                = "RABBITMQ"
      engine_version        = "4.2"
      instance_type         = var.mq_instance_type
      deployment_mode       = "SINGLE_INSTANCE"
      publicly_accessible   = false
      isolated_subnet_count = 1
      encrypted             = true
      tls_port              = 5671
    }
    secrets = {
      generated             = ["database", "broker"]
      injected_by_reference = true
      output_values         = false
      immediate_destroy     = true
    }
  }
}
