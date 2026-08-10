output "vpc_id" {
  value = aws_vpc.environment.id
}

output "public_task_subnet_ids" {
  value = [for index in sort(keys(aws_subnet.public_task)) : aws_subnet.public_task[index].id]
}

output "isolated_service_subnet_ids" {
  value = [for index in sort(keys(aws_subnet.isolated_service)) : aws_subnet.isolated_service[index].id]
}

output "security_group_ids" {
  value = { for name, security_group in aws_security_group.environment : replace(name, "-", "_") => security_group.id }
}

output "static_contract" {
  value = {
    nat_resources              = 0
    internet_gateway_count     = 1
    public_task_subnet_count   = 2
    isolated_subnet_count      = 2
    public_task_default_route  = "internet-gateway"
    isolated_default_routes    = 0
    s3_gateway_endpoint_routes = ["public-task"]
    public_inbound_cidrs       = []
    security_group_edges = [
      { from = "api-gateway-vpc-link", to = "web", protocol = "tcp", port = 3000 },
      { from = "api-gateway-vpc-link", to = "api", protocol = "tcp", port = 8000 },
      { from = "api", to = "postgresql", protocol = "tcp", port = 5432 },
      { from = "api", to = "rabbitmq", protocol = "tcp", port = 5671 },
      { from = "ml", to = "rabbitmq", protocol = "tcp", port = 5671 },
    ]
  }
}
