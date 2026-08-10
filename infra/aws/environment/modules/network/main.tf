locals {
  subnet_indexes = toset(["0", "1"])
  resolver_cidr  = "${cidrhost(var.vpc_cidr, 2)}/32"
  security_group_names = toset([
    "vpc-link",
    "web",
    "api",
    "ml",
    "database",
    "broker",
  ])
}

resource "aws_vpc" "environment" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
}

resource "aws_internet_gateway" "environment" {
  vpc_id = aws_vpc.environment.id
}

resource "aws_subnet" "public_task" {
  for_each = local.subnet_indexes

  vpc_id                  = aws_vpc.environment.id
  availability_zone       = var.availability_zones[tonumber(each.key)]
  cidr_block              = var.public_task_subnet_cidrs[tonumber(each.key)]
  map_public_ip_on_launch = false
}

resource "aws_subnet" "isolated_service" {
  for_each = local.subnet_indexes

  vpc_id                  = aws_vpc.environment.id
  availability_zone       = var.availability_zones[tonumber(each.key)]
  cidr_block              = var.isolated_service_subnet_cidrs[tonumber(each.key)]
  map_public_ip_on_launch = false
}

resource "aws_route_table" "public_task" {
  vpc_id = aws_vpc.environment.id
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public_task.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.environment.id
}

resource "aws_route_table_association" "public_task" {
  for_each = aws_subnet.public_task

  subnet_id      = each.value.id
  route_table_id = aws_route_table.public_task.id
}

resource "aws_route_table" "isolated_service" {
  vpc_id = aws_vpc.environment.id
}

resource "aws_route_table_association" "isolated_service" {
  for_each = aws_subnet.isolated_service

  subnet_id      = each.value.id
  route_table_id = aws_route_table.isolated_service.id
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.environment.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.public_task.id]
}

resource "aws_security_group" "environment" {
  for_each = local.security_group_names

  name                   = "${var.name}-${each.key}"
  description            = "Exact ${each.key} edge for the managed ephemeral environment"
  vpc_id                 = aws_vpc.environment.id
  revoke_rules_on_delete = true
}

resource "aws_vpc_security_group_egress_rule" "vpc_link_to_web" {
  security_group_id            = aws_security_group.environment["vpc-link"].id
  referenced_security_group_id = aws_security_group.environment["web"].id
  ip_protocol                  = "tcp"
  from_port                    = 3000
  to_port                      = 3000
}

resource "aws_vpc_security_group_ingress_rule" "web_from_vpc_link" {
  security_group_id            = aws_security_group.environment["web"].id
  referenced_security_group_id = aws_security_group.environment["vpc-link"].id
  ip_protocol                  = "tcp"
  from_port                    = 3000
  to_port                      = 3000
}

resource "aws_vpc_security_group_egress_rule" "vpc_link_to_api" {
  security_group_id            = aws_security_group.environment["vpc-link"].id
  referenced_security_group_id = aws_security_group.environment["api"].id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}

resource "aws_vpc_security_group_ingress_rule" "api_from_vpc_link" {
  security_group_id            = aws_security_group.environment["api"].id
  referenced_security_group_id = aws_security_group.environment["vpc-link"].id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}

resource "aws_vpc_security_group_egress_rule" "api_to_database" {
  security_group_id            = aws_security_group.environment["api"].id
  referenced_security_group_id = aws_security_group.environment["database"].id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_vpc_security_group_ingress_rule" "database_from_api" {
  security_group_id            = aws_security_group.environment["database"].id
  referenced_security_group_id = aws_security_group.environment["api"].id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_vpc_security_group_egress_rule" "broker_clients" {
  for_each = toset(["api", "ml"])

  security_group_id            = aws_security_group.environment[each.key].id
  referenced_security_group_id = aws_security_group.environment["broker"].id
  ip_protocol                  = "tcp"
  from_port                    = 5671
  to_port                      = 5671
}

resource "aws_vpc_security_group_ingress_rule" "broker_from_clients" {
  for_each = toset(["api", "ml"])

  security_group_id            = aws_security_group.environment["broker"].id
  referenced_security_group_id = aws_security_group.environment[each.key].id
  ip_protocol                  = "tcp"
  from_port                    = 5671
  to_port                      = 5671
}

resource "aws_vpc_security_group_egress_rule" "task_https" {
  for_each = toset(["web", "api", "ml"])

  security_group_id = aws_security_group.environment[each.key].id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_egress_rule" "task_dns_udp" {
  for_each = toset(["web", "api", "ml"])

  security_group_id = aws_security_group.environment[each.key].id
  cidr_ipv4         = local.resolver_cidr
  ip_protocol       = "udp"
  from_port         = 53
  to_port           = 53
}
resource "aws_vpc_security_group_egress_rule" "task_dns_tcp" {
  for_each = toset(["web", "api", "ml"])

  security_group_id = aws_security_group.environment[each.key].id
  cidr_ipv4         = local.resolver_cidr
  ip_protocol       = "tcp"
  from_port         = 53
  to_port           = 53
}
