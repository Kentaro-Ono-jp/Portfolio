mock_provider "aws" {
  override_during = plan

  mock_resource "aws_apigatewayv2_api" {
    defaults = {
      api_endpoint = "https://api.example.test"
    }
  }

  mock_resource "aws_cognito_user_pool" {
    defaults = {
      id = "us-east-1_example"
    }
  }

  mock_resource "aws_cognito_user_pool_client" {
    defaults = {
      id = "synthetic-public-client"
    }
  }
}

mock_provider "random" {
  override_during = plan

  mock_resource "random_password" {
    defaults = {
      result = "synthetic-generated-value"
    }
  }
}

variables {
  aws_account_id = "111122223333"
  aws_partition  = "aws"
  aws_region     = "us-east-1"
  availability_zones = [
    "us-east-1a",
    "us-east-1b",
  ]

  name_prefix           = "example-portfolio"
  repository_identity   = "example-owner/example-repository"
  environment           = "manual"
  environment_state_key = "environments/manual/terraform.tfstate"

  bootstrap_role_arns = {
    operator_deployment = "arn:aws:iam::111122223333:role/example-portfolio/example-portfolio-manual-operator-deployment"
    task_execution      = "arn:aws:iam::111122223333:role/example-portfolio/example-portfolio-manual-task-execution"
    web_workload        = "arn:aws:iam::111122223333:role/example-portfolio/example-portfolio-manual-web-workload"
    api_workload        = "arn:aws:iam::111122223333:role/example-portfolio/example-portfolio-manual-api-workload"
    ml_workload         = "arn:aws:iam::111122223333:role/example-portfolio/example-portfolio-manual-ml-workload"
    destroy             = "arn:aws:iam::111122223333:role/example-portfolio/example-portfolio-manual-destroy"
  }

  ecr_repository_urls = {
    web = "111122223333.dkr.ecr.us-east-1.amazonaws.com/example-portfolio/web"
    api = "111122223333.dkr.ecr.us-east-1.amazonaws.com/example-portfolio/api"
    ml  = "111122223333.dkr.ecr.us-east-1.amazonaws.com/example-portfolio/ml"
  }
  image_digests = {
    web = "sha256:1111111111111111111111111111111111111111111111111111111111111111"
    api = "sha256:2222222222222222222222222222222222222222222222222222222222222222"
    ml  = "sha256:3333333333333333333333333333333333333333333333333333333333333333"
  }

  vpc_cidr = "10.42.0.0/16"
  public_task_subnet_cidrs = [
    "10.42.0.0/24",
    "10.42.1.0/24",
  ]
  isolated_service_subnet_cidrs = [
    "10.42.10.0/24",
    "10.42.11.0/24",
  ]

  rds_instance_class     = "db.t4g.micro"
  mq_instance_type       = "mq.m7g.large"
  log_retention_days     = 3
  object_expiration_days = 2
  reviewer_group_name    = "reactorfront-reviewers"
  oidc_api_audience      = "https://api.example.invalid/api"
}

run "portable_environment_contract" {
  command = plan

  assert {
    condition = (
      output.ownership_contract.environment_state_key == "environments/manual/terraform.tfstate" &&
      output.ownership_contract.tags == {
        PortfolioEnvironment = "manual"
        PortfolioManaged     = "true"
        PortfolioPersistent  = "false"
        PortfolioRepository  = "example-owner/example-repository"
      }
    )
    error_message = "The environment must have one exact state key and four exact ownership tags."
  }

  assert {
    condition = (
      output.static_contract.network.nat_resources == 0 &&
      output.static_contract.network.public_task_subnet_count == 2 &&
      output.static_contract.network.isolated_subnet_count == 2 &&
      output.static_contract.network.isolated_default_routes == 0 &&
      length(output.static_contract.network.public_inbound_cidrs) == 0 &&
      length(output.static_contract.network.security_group_edges) == 5 &&
      contains(output.static_contract.network.security_group_edges, {
        from     = "api-gateway-vpc-link"
        to       = "api"
        protocol = "tcp"
        port     = 8000
      })
    )
    error_message = "The NAT-free topology must include the exact VPC Link to API service edge."
  }

  assert {
    condition = (
      output.static_contract.ingress.public_boundary == "api-gateway-http-api-generated-https" &&
      output.static_contract.ingress.integration_connection == "VPC_LINK" &&
      output.static_contract.ingress.integration_target == "cloud-map:web" &&
      output.static_contract.ingress.api_integration_target == "cloud-map:api" &&
      output.static_contract.ingress.generated_https_apis == 2 &&
      output.static_contract.ingress.alb_resources == 0 &&
      output.static_contract.ingress.custom_domain_resources == 0
    )
    error_message = "Ingress must use only two generated HTTP API endpoints, one VPC Link, and the Web/API Cloud Map targets."
  }

  assert {
    condition = (
      output.static_contract.runtime.network_mode == "awsvpc" &&
      output.static_contract.runtime.public_ip_assignment &&
      output.static_contract.runtime.tasks.web.cpu == 256 &&
      output.static_contract.runtime.tasks.api.cpu == 512 &&
      output.static_contract.runtime.tasks.ml.cpu == 1024 &&
      length(output.static_contract.runtime.tasks.api.containers) == 3 &&
      output.static_contract.runtime.tasks.ml.database_secret == false &&
      output.static_contract.runtime.tasks.ml.end_user_identity == false &&
      output.static_contract.runtime.web_application_store_credentials == false
    )
    error_message = "ECS must preserve measured sizing, process boundaries, role separation, and data boundaries."
  }

  assert {
    condition = alltrue([
      for reference in values(output.bootstrap_references.image_references) :
      can(regex("@sha256:[0-9a-f]{64}$", reference))
    ])
    error_message = "Every ECS image reference must be digest pinned."
  }

  assert {
    condition = (
      output.static_contract.state.postgresql.engine_version == "18" &&
      output.static_contract.state.postgresql.single_az &&
      output.static_contract.state.postgresql.encrypted &&
      !output.static_contract.state.postgresql.publicly_accessible &&
      output.static_contract.state.object_store.force_destroy &&
      output.static_contract.state.object_store.public_access_blocked &&
      output.static_contract.state.rabbitmq.engine_version == "4.2" &&
      output.static_contract.state.rabbitmq.deployment_mode == "SINGLE_INSTANCE" &&
      !output.static_contract.state.rabbitmq.publicly_accessible
    )
    error_message = "Managed state must remain encrypted, isolated, evaluation-sized, and environment-destroyable."
  }

  assert {
    condition = (
      output.static_contract.identity.public_client &&
      !output.static_contract.identity.client_secret_generated &&
      output.static_contract.identity.authorization_code_flow &&
      output.static_contract.identity.pkce_required &&
      output.static_contract.identity.managed_login_version == 2 &&
      !output.static_contract.identity.public_signup &&
      output.static_contract.identity.seeded_users == 0 &&
      output.static_contract.identity.capability_claim == "cognito:groups"
    )
    error_message = "Cognito must preserve the public PKCE client, managed login, and accepted group boundary without seeding users."
  }
}

run "reject_mutable_image_selection" {
  command = plan

  variables {
    image_digests = {
      web = "latest"
      api = "sha256:2222222222222222222222222222222222222222222222222222222222222222"
      ml  = "sha256:3333333333333333333333333333333333333333333333333333333333333333"
    }
  }

  expect_failures = [var.image_digests]
}

run "accept_console_owned_root_roles" {
  command = plan

  variables {
    bootstrap_role_arns = {
      operator_deployment = "arn:aws:iam::111122223333:role/example-portfolio-manual-operator-deployment"
      task_execution      = "arn:aws:iam::111122223333:role/example-portfolio-manual-task-execution"
      web_workload        = "arn:aws:iam::111122223333:role/example-portfolio-manual-web-workload"
      api_workload        = "arn:aws:iam::111122223333:role/example-portfolio-manual-api-workload"
      ml_workload         = "arn:aws:iam::111122223333:role/example-portfolio-manual-ml-workload"
      destroy             = "arn:aws:iam::111122223333:role/example-portfolio-manual-destroy"
    }
  }

  assert {
    condition = (
      output.bootstrap_references.role_arns.task_execution ==
      "arn:aws:iam::111122223333:role/example-portfolio-manual-task-execution"
    )
    error_message = "The environment must accept the exact Console-owned root role form."
  }
}

run "reject_cross_environment_state_key" {
  command = plan

  variables {
    environment_state_key = "environments/monthly/terraform.tfstate"
  }

  expect_failures = [var.environment_state_key]
}
