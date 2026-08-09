variable "name" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "public_task_subnet_ids" {
  type = list(string)
}

variable "vpc_link_security_group_id" {
  type = string
}

variable "log_path_prefix" {
  type = string
}

variable "log_retention_days" {
  type = number
}
