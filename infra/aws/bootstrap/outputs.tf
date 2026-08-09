output "backend_contract" {
  description = "Partial S3 backend settings; supply them explicitly during migration and every later init."
  value = {
    bucket              = aws_s3_bucket.terraform_state.bucket
    bootstrap_state_key = var.bootstrap_state_key
    environment_keys    = var.environment_state_keys
    encrypt             = true
    region              = var.aws_region
    use_lockfile        = true
  }
}

output "ecr_repository_urls" {
  description = "Independent immutable repositories; later deployment must select image digests, never mutable tags."
  value = {
    for purpose, repository in aws_ecr_repository.application :
    purpose => repository.repository_url
  }
}

output "permissions_boundary_arn" {
  description = "Fixed boundary required on every delegable Portfolio role."
  value       = aws_iam_policy.permissions_boundary.arn
}

output "global_role_arns" {
  description = "Shared IAM-manager and future automation authorities."
  value = {
    for purpose, role in aws_iam_role.global : purpose => role.arn
  }
}

output "environment_role_arns" {
  description = "One-purpose, environment-isolated operator, task, workload, fallback, and destroy authorities."
  value = {
    for purpose, role in aws_iam_role.environment : purpose => role.arn
  }
}

output "github_trust_contract" {
  description = "Future automation must also enforce only workflow_dispatch and schedule in the named workflow."
  value = {
    allowed_events = ["schedule", "workflow_dispatch"]
    audience       = "sts.amazonaws.com"
    environment    = var.github_environment
    ref            = "refs/heads/main"
    repository     = var.repository_identity
    subject        = local.github_oidc_subject
    workflow       = var.github_workflow_name
    workflow_ref   = var.github_workflow_ref
  }
}
