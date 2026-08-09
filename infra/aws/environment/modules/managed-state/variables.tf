variable "name" {
  type = string
}

variable "aws_partition" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "isolated_service_subnet_ids" {
  type = list(string)
}

variable "database_security_group_id" {
  type = string
}

variable "broker_security_group_id" {
  type = string
}

variable "rds_instance_class" {
  type = string
}

variable "mq_instance_type" {
  type = string
}

variable "object_expiration_days" {
  type = number
}
