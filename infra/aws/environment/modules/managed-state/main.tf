locals {
  database_name     = "portfolio"
  database_username = "portfolio"
  broker_username   = "portfolio"
  bucket_name       = "${var.name}-documents"
  bucket_arn        = "arn:${var.aws_partition}:s3:::${local.bucket_name}"
}

resource "random_password" "database" {
  length  = 32
  special = false
}

resource "random_password" "broker" {
  length  = 32
  special = false
}

resource "aws_db_subnet_group" "environment" {
  name       = var.name
  subnet_ids = var.isolated_service_subnet_ids
}

resource "aws_db_instance" "postgresql" {
  identifier                   = "${var.name}-postgresql"
  engine                       = "postgres"
  engine_version               = "18"
  engine_lifecycle_support     = "open-source-rds-extended-support-disabled"
  instance_class               = var.rds_instance_class
  allocated_storage            = 20
  storage_type                 = "gp3"
  storage_encrypted            = true
  db_name                      = local.database_name
  username                     = local.database_username
  password                     = random_password.database.result
  port                         = 5432
  multi_az                     = false
  publicly_accessible          = false
  db_subnet_group_name         = aws_db_subnet_group.environment.name
  vpc_security_group_ids       = [var.database_security_group_id]
  backup_retention_period      = 0
  copy_tags_to_snapshot        = false
  deletion_protection          = false
  delete_automated_backups     = true
  skip_final_snapshot          = true
  auto_minor_version_upgrade   = true
  apply_immediately            = true
  performance_insights_enabled = false
}

resource "aws_mq_broker" "rabbitmq" {
  broker_name                = "${var.name}-rabbitmq"
  engine_type                = "RabbitMQ"
  engine_version             = "4.2"
  host_instance_type         = var.mq_instance_type
  deployment_mode            = "SINGLE_INSTANCE"
  storage_type               = "ebs"
  authentication_strategy    = "simple"
  publicly_accessible        = false
  subnet_ids                 = [var.isolated_service_subnet_ids[0]]
  security_groups            = [var.broker_security_group_id]
  auto_minor_version_upgrade = true
  apply_immediately          = true

  encryption_options {
    use_aws_owned_key = true
  }

  maintenance_window_start_time {
    day_of_week = "SUNDAY"
    time_of_day = "03:00"
    time_zone   = "UTC"
  }

  user {
    username       = local.broker_username
    password       = random_password.broker.result
    console_access = false
  }
}

resource "aws_s3_bucket" "application" {
  bucket        = local.bucket_name
  force_destroy = true
}

resource "aws_s3_bucket_ownership_controls" "application" {
  bucket = aws_s3_bucket.application.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "application" {
  bucket = aws_s3_bucket.application.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "application" {
  bucket = aws_s3_bucket.application.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "application" {
  bucket = aws_s3_bucket.application.id

  rule {
    id     = "expire-ephemeral-objects"
    status = "Enabled"

    filter {}

    expiration {
      days = var.object_expiration_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

resource "aws_s3_bucket_policy" "application" {
  bucket = aws_s3_bucket.application.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [local.bucket_arn, "${local.bucket_arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })

  depends_on = [aws_s3_bucket_public_access_block.application]
}

resource "aws_secretsmanager_secret" "database" {
  name                    = "${var.name}-database"
  description             = "Generated ephemeral PostgreSQL runtime connection"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "database" {
  secret_id = aws_secretsmanager_secret.database.id
  secret_string = jsonencode({
    database_url = format(
      "postgresql+psycopg://%s:%s@%s:%s/%s",
      local.database_username,
      urlencode(random_password.database.result),
      aws_db_instance.postgresql.address,
      aws_db_instance.postgresql.port,
      local.database_name,
    )
  })
}

resource "aws_secretsmanager_secret" "broker" {
  name                    = "${var.name}-broker"
  description             = "Generated ephemeral RabbitMQ runtime connection"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "broker" {
  secret_id = aws_secretsmanager_secret.broker.id
  secret_string = jsonencode({
    broker_url = format(
      "amqps://%s:%s@%s/%%2F",
      local.broker_username,
      urlencode(random_password.broker.result),
      trimprefix(aws_mq_broker.rabbitmq.instances[0].endpoints[0], "amqps://"),
    )
  })
}
