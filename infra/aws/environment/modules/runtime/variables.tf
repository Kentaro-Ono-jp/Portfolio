variable "name" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "public_task_subnet_ids" {
  type = list(string)
}

variable "security_group_ids" {
  type = object({
    vpc_link = string
    web      = string
    api      = string
    ml       = string
    database = string
    broker   = string
  })
}

variable "cloud_map" {
  type = object({
    namespace_id    = string
    namespace_name  = string
    web_service_arn = string
    api_service_arn = string
    web_dns_name    = string
    api_dns_name    = string
  })
}

variable "public_web_base_url" {
  type = string
}

variable "identity" {
  type = object({
    issuer            = string
    authorization_url = string
    discovery_url     = string
    token_url         = string
    jwks_url          = string
    client_id         = string
    scopes            = string
    audience          = string
    capability_claim  = string
    reviewer_group    = string
  })
}

variable "application_bucket_name" {
  type = string
}

variable "runtime_secret_arns" {
  type = object({
    database = string
    broker   = string
  })
}

variable "image_references" {
  type = object({
    web = string
    api = string
    ml  = string
  })
}

variable "runtime_sizing" {
  type = object({
    schemaVersion = number
    tasks = map(object({
      cpuUnits  = number
      memoryMiB = number
    }))
    processes = map(object({
      task               = string
      memoryCandidateMiB = number
      concurrent         = bool
      imageService       = optional(string)
    }))
    measurement = object({
      minimumSamples          = number
      sampleIntervalSeconds   = number
      minimumHeadroomFraction = number
      workload                = string
      uncertainty             = string
    })
  })
}

variable "task_execution_role_arn" {
  type = string
}

variable "workload_role_arns" {
  type = object({
    web = string
    api = string
    ml  = string
  })
}

variable "log_path_prefix" {
  type = string
}

variable "log_retention_days" {
  type = number
}
