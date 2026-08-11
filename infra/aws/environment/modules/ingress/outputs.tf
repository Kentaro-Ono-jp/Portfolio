output "public_api_endpoint" {
  value = aws_apigatewayv2_api.web.api_endpoint
}

output "api_endpoint" {
  value = aws_apigatewayv2_api.api.api_endpoint
}

output "cloud_map" {
  value = {
    namespace_id    = aws_service_discovery_private_dns_namespace.environment.id
    namespace_name  = aws_service_discovery_private_dns_namespace.environment.name
    web_service_arn = aws_service_discovery_service.application["web"].arn
    api_service_arn = aws_service_discovery_service.application["api"].arn
    web_dns_name    = "web.${aws_service_discovery_private_dns_namespace.environment.name}"
    api_dns_name    = "api.${aws_service_discovery_private_dns_namespace.environment.name}"
  }
}

output "static_contract" {
  value = {
    public_boundary         = "api-gateway-http-api-generated-https"
    integration_type        = "HTTP_PROXY"
    integration_target      = "cloud-map:web"
    api_integration_target  = "cloud-map:api"
    generated_https_apis    = 2
    integration_connection  = "VPC_LINK"
    custom_domain_resources = 0
    alb_resources           = 0
    api_throttling = {
      burst = 20
      rate  = 10
    }
    gateway_log_retention_days = var.log_retention_days
  }
}
