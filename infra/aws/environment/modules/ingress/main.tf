resource "aws_service_discovery_private_dns_namespace" "environment" {
  name        = "${var.name}.internal"
  description = "Private Web and API discovery for ${var.name}"
  vpc         = var.vpc_id
}

resource "aws_service_discovery_service" "application" {
  for_each = {
    web = 3000
    api = 8000
  }

  name          = each.key
  namespace_id  = aws_service_discovery_private_dns_namespace.environment.id
  force_destroy = true

  dns_config {
    namespace_id   = aws_service_discovery_private_dns_namespace.environment.id
    routing_policy = "MULTIVALUE"

    dns_records {
      ttl  = 10
      type = "SRV"
    }
  }
}

resource "aws_apigatewayv2_vpc_link" "web" {
  name               = "${var.name}-web"
  security_group_ids = [var.vpc_link_security_group_id]
  subnet_ids         = var.public_task_subnet_ids
}

resource "aws_apigatewayv2_api" "web" {
  name                         = "${var.name}-web"
  protocol_type                = "HTTP"
  disable_execute_api_endpoint = false
}

resource "aws_apigatewayv2_api" "api" {
  name                         = "${var.name}-api"
  protocol_type                = "HTTP"
  disable_execute_api_endpoint = false
}

resource "aws_apigatewayv2_integration" "web" {
  api_id                 = aws_apigatewayv2_api.web.id
  integration_type       = "HTTP_PROXY"
  integration_uri        = aws_service_discovery_service.application["web"].arn
  integration_method     = "ANY"
  connection_type        = "VPC_LINK"
  connection_id          = aws_apigatewayv2_vpc_link.web.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 29000
}

resource "aws_apigatewayv2_integration" "api" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "HTTP_PROXY"
  integration_uri        = aws_service_discovery_service.application["api"].arn
  integration_method     = "ANY"
  connection_type        = "VPC_LINK"
  connection_id          = aws_apigatewayv2_vpc_link.web.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 29000
}

resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.web.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.web.id}"
}

resource "aws_apigatewayv2_route" "api_default" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_cloudwatch_log_group" "gateway" {
  name              = "${var.log_path_prefix}/gateway"
  retention_in_days = var.log_retention_days
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.web.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.gateway.arn
    format = jsonencode({
      httpMethod       = "$context.httpMethod"
      integrationError = "$context.integrationErrorMessage"
      requestId        = "$context.requestId"
      routeKey         = "$context.routeKey"
      status           = "$context.status"
    })
  }

  default_route_settings {
    detailed_metrics_enabled = false
    throttling_burst_limit   = 20
    throttling_rate_limit    = 10
  }
}

resource "aws_apigatewayv2_stage" "api_default" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.gateway.arn
    format = jsonencode({
      httpMethod       = "$context.httpMethod"
      integrationError = "$context.integrationErrorMessage"
      requestId        = "$context.requestId"
      routeKey         = "$context.routeKey"
      status           = "$context.status"
    })
  }

  default_route_settings {
    detailed_metrics_enabled = false
    throttling_burst_limit   = 20
    throttling_rate_limit    = 10
  }
}
