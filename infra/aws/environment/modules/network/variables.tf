variable "name" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "availability_zones" {
  type = list(string)
}

variable "vpc_cidr" {
  type = string
}

variable "public_task_subnet_cidrs" {
  type = list(string)
}

variable "isolated_service_subnet_cidrs" {
  type = list(string)
}
