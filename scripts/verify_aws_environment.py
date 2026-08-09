from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterator


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENT_ROOT = REPOSITORY_ROOT / "infra" / "aws" / "environment"
OPERATOR_ACTION_MATRIX_PATH = ENVIRONMENT_ROOT / "operator-action-matrix.json"
CONSOLE_IAM_ROOT = ENVIRONMENT_ROOT / "console-iam"
ARTIFACT_PATH = (
    REPOSITORY_ROOT / "artifacts" / "verification" / "aws-environment-static.json"
)
TFVARS_PATH = "terraform.tfvars.example"
OWNERSHIP_TAGS = {
    "PortfolioEnvironment": "manual",
    "PortfolioManaged": "true",
    "PortfolioPersistent": "false",
    "PortfolioRepository": "example-owner/example-repository",
}
EXPECTED_RESOURCE_COUNTS = {
    "aws_apigatewayv2_api": 1,
    "aws_apigatewayv2_integration": 1,
    "aws_apigatewayv2_route": 1,
    "aws_apigatewayv2_stage": 1,
    "aws_apigatewayv2_vpc_link": 1,
    "aws_cloudwatch_log_group": 5,
    "aws_cognito_managed_login_branding": 1,
    "aws_cognito_resource_server": 1,
    "aws_cognito_user_group": 1,
    "aws_cognito_user_pool": 1,
    "aws_cognito_user_pool_client": 1,
    "aws_cognito_user_pool_domain": 1,
    "aws_db_instance": 1,
    "aws_db_subnet_group": 1,
    "aws_ecs_cluster": 1,
    "aws_ecs_service": 3,
    "aws_ecs_task_definition": 4,
    "aws_internet_gateway": 1,
    "aws_mq_broker": 1,
    "aws_route": 1,
    "aws_route_table": 2,
    "aws_route_table_association": 4,
    "aws_s3_bucket": 1,
    "aws_s3_bucket_lifecycle_configuration": 1,
    "aws_s3_bucket_ownership_controls": 1,
    "aws_s3_bucket_policy": 1,
    "aws_s3_bucket_public_access_block": 1,
    "aws_s3_bucket_server_side_encryption_configuration": 1,
    "aws_secretsmanager_secret": 2,
    "aws_secretsmanager_secret_version": 2,
    "aws_security_group": 6,
    "aws_service_discovery_private_dns_namespace": 1,
    "aws_service_discovery_service": 2,
    "aws_subnet": 4,
    "aws_vpc": 1,
    "aws_vpc_endpoint": 1,
    "aws_vpc_security_group_egress_rule": 14,
    "aws_vpc_security_group_ingress_rule": 5,
    "random_password": 2,
}
FORBIDDEN_RESOURCE_TYPES = {
    "aws_acm_certificate",
    "aws_alb",
    "aws_cloudfront_distribution",
    "aws_eip",
    "aws_instance",
    "aws_lb",
    "aws_nat_gateway",
    "aws_route53_record",
    "aws_route53_zone",
    "aws_waf_web_acl",
    "aws_wafv2_web_acl",
}
OPERATOR_ACTION_OWNERSHIP_MODES = {
    "exact-resource",
    "exact-resource-and-request-tags",
    "global-read",
    "owner-accepted-global-tagging",
    "request-tags",
    "resource-and-request-tags",
    "resource-tags",
    "service-delegated",
}
CLOUD_MAP_DELEGATED_ACTIONS = {
    "ec2:DescribeRegions",
    "route53:CreateHostedZone",
    "route53:GetHostedZone",
    "route53:ListHostedZonesByName",
}
REVIEWED_API_GATEWAY_IAM_ACTIONS = {
    "apigateway:*",
    "apigateway:DELETE",
    "apigateway:GET",
    "apigateway:POST",
}
CONSOLE_IAM_TOKENS = {
    "AWS_ACCOUNT_ID": "111122223333",
    "AWS_PARTITION": "aws",
    "AWS_REGION": "us-east-1",
    "ENVIRONMENT": "manual",
    "NAME_PREFIX": "example-portfolio",
    "REPOSITORY_IDENTITY": "example-owner/example-repository",
    "STATE_BUCKET_NAME": "example-portfolio-111122223333-us-east-1-state",
}
MANAGED_POLICY_CHARACTER_LIMIT = 6_144
MANAGED_POLICY_CHARACTER_RESERVE = 512
TRUST_POLICY_CHARACTER_LIMIT = 2_048
TRUST_POLICY_CHARACTER_RESERVE = 256


def string_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def rendered_console_json(path: Path) -> dict[str, Any]:
    rendered = path.read_text(encoding="utf-8")
    for token, value in CONSOLE_IAM_TOKENS.items():
        rendered = rendered.replace(f"${{{token}}}", value)
    if "${" in rendered:
        raise RuntimeError(f"Console IAM document has an unknown token: {path}")
    payload = json.loads(rendered)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Console IAM document must be an object: {path}")
    return payload


def enforce_policy_character_reserve(
    documents: dict[str, dict[str, Any]],
    *,
    limit: int,
    reserve: int,
    policy_class: str,
) -> dict[str, int]:
    sizes = {
        key: len(json.dumps(document, separators=(",", ":"), ensure_ascii=False))
        for key, document in documents.items()
    }
    oversized = {key: size for key, size in sizes.items() if size > limit - reserve}
    if oversized:
        raise RuntimeError(
            f"Console IAM {policy_class} exhausted its required "
            f"{reserve}-character reserve: {oversized}"
        )
    return sizes


def condition_matches(statement: dict[str, Any], context: dict[str, Any]) -> bool:
    conditions = statement.get("Condition", {})
    for operator, entries in conditions.items():
        if operator not in {
            "ForAllValues:StringEquals",
            "ForAnyValue:StringEquals",
            "StringEquals",
            "StringLike",
        }:
            return False
        for key, expected in entries.items():
            actual = context.get(key)
            if actual is None:
                return False
            expected_values = string_values(expected)
            actual_values = string_values(actual)
            if operator == "ForAllValues:StringEquals" and not all(
                value in expected_values for value in actual_values
            ):
                return False
            if operator in {"ForAnyValue:StringEquals", "StringEquals"} and not any(
                value in expected_values for value in actual_values
            ):
                return False
            if operator == "StringLike" and not any(
                fnmatch.fnmatchcase(value, candidate)
                for value in actual_values
                for candidate in expected_values
            ):
                return False
    return True


def policy_allows(
    policy: dict[str, Any],
    action: str,
    resource: str,
    context: dict[str, Any] | None = None,
) -> bool:
    normalized_action = action.lower()
    for statement in policy.get("Statement", []):
        if statement.get("Effect") != "Allow":
            continue
        actions = [
            value.lower() for value in string_values(statement.get("Action", []))
        ]
        resources = string_values(statement.get("Resource", []))
        if not any(
            fnmatch.fnmatchcase(normalized_action, pattern) for pattern in actions
        ):
            continue
        if not any(fnmatch.fnmatchcase(resource, pattern) for pattern in resources):
            continue
        if condition_matches(statement, context or {}):
            return True
    return False


def operator_resource(symbol: str) -> str:
    partition = CONSOLE_IAM_TOKENS["AWS_PARTITION"]
    account = CONSOLE_IAM_TOKENS["AWS_ACCOUNT_ID"]
    region = CONSOLE_IAM_TOKENS["AWS_REGION"]
    prefix = CONSOLE_IAM_TOKENS["NAME_PREFIX"]
    environment = CONSOLE_IAM_TOKENS["ENVIRONMENT"]
    if symbol == "*":
        return "*"
    if symbol == "app-bucket":
        return f"arn:{partition}:s3:::{prefix}-{environment}-documents"
    if symbol == "route53-hosted-zone":
        return f"arn:{partition}:route53:::hostedzone/owned-zone"
    if symbol.startswith("iam-"):
        purpose = symbol.removeprefix("iam-").removesuffix("-role")
        return f"arn:{partition}:iam::{account}:role/{prefix}-{environment}-{purpose}"
    resources = {
        "api-gateway-api-collection": f"arn:{partition}:apigateway:{region}::/apis",
        "api-gateway-api": f"arn:{partition}:apigateway:{region}::/apis/api-owned",
        "api-gateway-integration-collection": f"arn:{partition}:apigateway:{region}::/apis/api-owned/integrations",
        "api-gateway-integration": f"arn:{partition}:apigateway:{region}::/apis/api-owned/integrations/integration-owned",
        "api-gateway-route-collection": f"arn:{partition}:apigateway:{region}::/apis/api-owned/routes",
        "api-gateway-route": f"arn:{partition}:apigateway:{region}::/apis/api-owned/routes/route-owned",
        "api-gateway-stage-collection": f"arn:{partition}:apigateway:{region}::/apis/api-owned/stages",
        "api-gateway-stage": f"arn:{partition}:apigateway:{region}::/apis/api-owned/stages/$default",
        "api-gateway-vpc-link-collection": f"arn:{partition}:apigateway:{region}::/vpclinks",
        "api-gateway-vpc-link": f"arn:{partition}:apigateway:{region}::/vpclinks/vpclink-owned",
        "cloudmap-namespace": f"arn:{partition}:servicediscovery:{region}:{account}:namespace/ns-owned",
        "cloudmap-service": f"arn:{partition}:servicediscovery:{region}:{account}:service/srv-owned",
        "cognito-user-pool": f"arn:{partition}:cognito-idp:{region}:{account}:userpool/{region}_owned",
        "ec2-internet-gateway": f"arn:{partition}:ec2:{region}:{account}:internet-gateway/igw-owned",
        "ec2-route-table": f"arn:{partition}:ec2:{region}:{account}:route-table/rtb-owned",
        "ec2-security-group": f"arn:{partition}:ec2:{region}:{account}:security-group/sg-owned",
        "ec2-security-group-rule": f"arn:{partition}:ec2:{region}:{account}:security-group-rule/sgr-owned",
        "ec2-subnet": f"arn:{partition}:ec2:{region}:{account}:subnet/subnet-owned",
        "ec2-vpc": f"arn:{partition}:ec2:{region}:{account}:vpc/vpc-owned",
        "ec2-vpc-endpoint": f"arn:{partition}:ec2:{region}:{account}:vpc-endpoint/vpce-owned",
        "ecs-cluster": f"arn:{partition}:ecs:{region}:{account}:cluster/{prefix}-{environment}",
        "ecs-service": f"arn:{partition}:ecs:{region}:{account}:service/{prefix}-{environment}/{prefix}-{environment}-web",
        "ecs-task-definition": f"arn:{partition}:ecs:{region}:{account}:task-definition/{prefix}-{environment}-web:1",
        "log-group": f"arn:{partition}:logs:{region}:{account}:log-group:/portfolio/{prefix}/{environment}/web",
        "mq-broker": f"arn:{partition}:mq:{region}:{account}:broker:{prefix}-{environment}-rabbitmq:broker-id",
        "rds-db": f"arn:{partition}:rds:{region}:{account}:db:{prefix}-{environment}-postgresql",
        "rds-subnet-group": f"arn:{partition}:rds:{region}:{account}:subgrp:{prefix}-{environment}",
        "secret": f"arn:{partition}:secretsmanager:{region}:{account}:secret:{prefix}-{environment}-database-abcdef",
    }
    if symbol not in resources:
        raise RuntimeError(f"Unknown operator resource symbol: {symbol}")
    return resources[symbol]


def foreign_operator_resource(symbol: str) -> str:
    resource = operator_resource(symbol)
    environment = CONSOLE_IAM_TOKENS["ENVIRONMENT"]
    if environment in resource:
        return resource.replace(environment, "monthly")
    replacements = {
        "/api-owned": "/api-foreign",
        "/vpclink-owned": "/vpclink-foreign",
        "/ns-owned": "/ns-foreign",
        "/srv-owned": "/srv-foreign",
        "_owned": "_foreign",
        "/igw-owned": "/igw-foreign",
        "/rtb-owned": "/rtb-foreign",
        "/sg-owned": "/sg-foreign",
        "/sgr-owned": "/sgr-foreign",
        "/subnet-owned": "/subnet-foreign",
        "/vpc-owned": "/vpc-foreign",
        "/vpce-owned": "/vpce-foreign",
        ":broker-id": ":foreign-id",
        "-abcdef": "-uvwxyz",
    }
    for owned, foreign in replacements.items():
        if owned in resource:
            return resource.replace(owned, foreign)
    raise RuntimeError(f"Cannot synthesize foreign operator resource: {symbol}")


def verify_console_iam_contract(matrix: dict[str, Any]) -> dict[str, Any]:
    manifest = rendered_console_json(CONSOLE_IAM_ROOT / "manifest.json")
    if manifest.get("schemaVersion") != 1:
        raise RuntimeError("Unknown Console IAM manifest schema")

    expected_policy_keys = {
        "noelAssumeBillingReadRole",
        "noelDeploymentAssumeOperator",
        "noelAssumeObserverRole",
        "operatorPermissions",
        "managedEnvironmentPermissions",
        "managedEnvironmentResourcePermissions",
        "operatorBoundary",
        "taskExecution",
        "apiWorkload",
        "mlWorkload",
        "destroy",
    }
    policy_specs = manifest.get("managedPolicies", {})
    if set(policy_specs) != expected_policy_keys:
        raise RuntimeError("Console IAM managed-policy inventory drifted")
    policy_names = [spec["name"] for spec in policy_specs.values()]
    policy_documents = [spec["document"] for spec in policy_specs.values()]
    if len(set(policy_names)) != len(policy_names):
        raise RuntimeError("Console IAM managed policies must be different objects")
    if len(set(policy_documents)) != len(policy_documents):
        raise RuntimeError("Console IAM managed policies must use different documents")

    policies = {
        key: rendered_console_json(CONSOLE_IAM_ROOT / spec["document"])
        for key, spec in policy_specs.items()
    }
    for key, policy in policies.items():
        statements = policy.get("Statement")
        if not isinstance(statements, list) or not statements:
            raise RuntimeError(f"Console IAM policy has no statements: {key}")
        if any(statement.get("Effect") == "Deny" for statement in statements):
            raise RuntimeError(
                f"Console IAM policy must not contain explicit Deny: {key}"
            )
        api_gateway_actions = {
            action
            for statement in statements
            for action in string_values(statement.get("Action", []))
            if action.startswith("apigateway:")
        }
        unknown_api_gateway_actions = (
            api_gateway_actions - REVIEWED_API_GATEWAY_IAM_ACTIONS
        )
        if unknown_api_gateway_actions:
            raise RuntimeError(
                "Console IAM policy uses an unreviewed API Gateway IAM action: "
                f"{key} {sorted(unknown_api_gateway_actions)}"
            )
    managed_policy_sizes = enforce_policy_character_reserve(
        policies,
        limit=MANAGED_POLICY_CHARACTER_LIMIT,
        reserve=MANAGED_POLICY_CHARACTER_RESERVE,
        policy_class="managed policy",
    )

    expected_service_linked_roles = {
        "apiGateway": {
            "roleName": "AWSServiceRoleForAPIGateway",
            "serviceName": "ops.apigateway.amazonaws.com",
        },
        "ecs": {
            "roleName": "AWSServiceRoleForECS",
            "serviceName": "ecs.amazonaws.com",
        },
        "mq": {
            "roleName": "AWSServiceRoleForAmazonMQ",
            "serviceName": "mq.amazonaws.com",
        },
        "rds": {
            "roleName": "AWSServiceRoleForRDS",
            "serviceName": "rds.amazonaws.com",
        },
    }
    if manifest.get("serviceLinkedRoles") != expected_service_linked_roles:
        raise RuntimeError("Console IAM service-linked role inventory drifted")

    expected_source_users = {
        "noel_deployment": {
            "name": "ReactorFrontNoel",
            "permissions": [
                "noelAssumeBillingReadRole",
                "noelDeploymentAssumeOperator",
                "noelAssumeObserverRole",
            ],
            "inlinePolicies": [],
            "groups": [],
            "boundary": None,
            "consoleLogin": False,
            "credentialMode": "existingAccessKey",
        }
    }
    if manifest.get("sourceUsers") != expected_source_users:
        raise RuntimeError("Console IAM deployment-source user contract drifted")

    exact_operator_role = (
        "arn:aws:iam::111122223333:role/example-portfolio-manual-operator-deployment"
    )
    exact_billing_read_role = (
        "arn:aws:iam::111122223333:role/ReactorFrontBillingReadRole"
    )
    exact_observer_role = "arn:aws:iam::111122223333:role/ReactorFrontObserverRole"
    expected_noel_policies = {
        "noelAssumeBillingReadRole": (
            "AssumeExactBillingReadRole",
            exact_billing_read_role,
        ),
        "noelDeploymentAssumeOperator": (
            "AssumeExactOperatorDeploymentRole",
            exact_operator_role,
        ),
        "noelAssumeObserverRole": (
            "AssumeExactObserverRole",
            exact_observer_role,
        ),
    }
    for policy_key, (sid, role_arn) in expected_noel_policies.items():
        expected_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": sid,
                    "Effect": "Allow",
                    "Action": "sts:AssumeRole",
                    "Resource": role_arn,
                }
            ],
        }
        if policies[policy_key] != expected_policy:
            raise RuntimeError(
                "Noel source user policies must each assume one exact approved role"
            )

    expected_roles = {
        "operator_deployment",
        "task_execution",
        "web_workload",
        "api_workload",
        "ml_workload",
        "destroy",
    }
    roles = manifest.get("roles", {})
    if set(roles) != expected_roles:
        raise RuntimeError("Console IAM role inventory drifted")
    for purpose, role in roles.items():
        expected_name = "example-portfolio-manual-" + purpose.replace("_", "-")
        if role.get("name") != expected_name:
            raise RuntimeError(f"Console IAM role name drifted: {purpose}")
        if role.get("boundary") != "operatorBoundary":
            raise RuntimeError(
                f"Console IAM role lost the separate boundary: {purpose}"
            )
    operator_permission_keys = [
        "operatorPermissions",
        "managedEnvironmentPermissions",
        "managedEnvironmentResourcePermissions",
    ]
    if roles["operator_deployment"].get("permissions") != operator_permission_keys:
        raise RuntimeError(
            "Operator must have exactly its separately named static permissions policies"
        )
    if roles["web_workload"].get("permissions") != []:
        raise RuntimeError("Web workload must remain an empty-authority role")
    if roles["destroy"].get("permissions") != ["operatorPermissions", "destroy"]:
        raise RuntimeError(
            "Destroy must combine backend reads with separate delete authority"
        )

    trust_files = {role["trust"] for role in roles.values()}
    trusts = {
        trust_file: rendered_console_json(CONSOLE_IAM_ROOT / trust_file)
        for trust_file in trust_files
    }
    for trust_file, trust in trusts.items():
        if any(
            statement.get("Effect") == "Deny"
            for statement in trust.get("Statement", [])
        ):
            raise RuntimeError(
                f"Console IAM trust must not contain explicit Deny: {trust_file}"
            )
    expected_operator_trust = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "ExactNoelDeploymentUser",
                "Effect": "Allow",
                "Principal": {
                    "AWS": ("arn:aws:iam::111122223333:user/ReactorFrontNoel")
                },
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {
                        "aws:PrincipalAccount": CONSOLE_IAM_TOKENS["AWS_ACCOUNT_ID"]
                    }
                },
            }
        ],
    }
    if trusts.get("operator-trust.json") != expected_operator_trust:
        raise RuntimeError(
            "Console operator trust must allow only the exact same-account owner "
            "principal without an MFA condition"
        )
    trust_policy_sizes = enforce_policy_character_reserve(
        trusts,
        limit=TRUST_POLICY_CHARACTER_LIMIT,
        reserve=TRUST_POLICY_CHARACTER_RESERVE,
        policy_class="trust policy",
    )

    permissions = {
        "Version": "2012-10-17",
        "Statement": [
            statement
            for key in operator_permission_keys
            for statement in policies[key]["Statement"]
        ],
    }
    boundary = policies["operatorBoundary"]
    destroy = policies["destroy"]
    rows = 0
    allowed_layer_decisions = 0
    reviewed_operator_rows: list[
        tuple[str, int, str, str, str, str, dict[str, Any]]
    ] = []
    for resource_type, action_rows in sorted(matrix["resourceActions"].items()):
        for row_index, row in enumerate(action_rows):
            action, symbol, ownership = row[:3]
            resource = operator_resource(symbol)
            context: dict[str, Any] = {}
            if ownership in {
                "exact-resource-and-request-tags",
                "owner-accepted-global-tagging",
                "request-tags",
                "resource-and-request-tags",
            }:
                context.update(
                    {
                        f"aws:RequestTag/{key}": value
                        for key, value in OWNERSHIP_TAGS.items()
                    }
                )
                context["aws:TagKeys"] = list(OWNERSHIP_TAGS)
            if ownership in {"resource-and-request-tags", "resource-tags"}:
                context.update(
                    {
                        f"aws:ResourceTag/{key}": value
                        for key, value in OWNERSHIP_TAGS.items()
                    }
                )
            context.update(dict(row[3] if len(row) == 4 else {}))
            decisions = (
                policy_allows(permissions, action, resource, context),
                policy_allows(boundary, action, resource, context),
            )
            if decisions != (True, True):
                raise RuntimeError(
                    "Console operator permissions × boundary cannot execute the "
                    f"reviewed provider action: {resource_type} {action} {symbol} "
                    f"got identity={decisions[0]} boundary={decisions[1]}"
                )
            rows += 1
            allowed_layer_decisions += 2
            reviewed_operator_rows.append(
                (
                    resource_type,
                    row_index,
                    action,
                    symbol,
                    ownership,
                    resource,
                    context,
                )
            )

    invariant_cases: dict[str, bool] = {}

    def record(name: str, passed: bool) -> None:
        if name in invariant_cases:
            raise RuntimeError(f"Duplicate Console IAM invariant: {name}")
        invariant_cases[name] = passed

    noel_identity = [policies[key] for key in expected_noel_policies]
    for label, resource in (
        ("ExactOperator", exact_operator_role),
        ("ExactBillingRead", exact_billing_read_role),
        ("ExactObserver", exact_observer_role),
    ):
        record(
            f"noelCanAssume{label}",
            any(
                policy_allows(policy, "sts:AssumeRole", resource)
                for policy in noel_identity
            ),
        )
    for label, action, resource in (
        (
            "DestroyRole",
            "sts:AssumeRole",
            "arn:aws:iam::111122223333:role/example-portfolio-manual-destroy",
        ),
        (
            "UnrelatedRole",
            "sts:AssumeRole",
            "arn:aws:iam::111122223333:role/unrelated-role",
        ),
        ("Ec2ResourceApi", "ec2:CreateVpc", "*"),
        (
            "S3ResourceApi",
            "s3:CreateBucket",
            "arn:aws:s3:::example-portfolio-manual-documents",
        ),
        (
            "RdsResourceApi",
            "rds:CreateDBInstance",
            "arn:aws:rds:us-east-1:111122223333:db:example-portfolio-manual-postgresql",
        ),
        ("IamResourceApi", "iam:ListUsers", "*"),
    ):
        record(
            f"noelCannotUse{label}",
            not any(
                policy_allows(policy, action, resource) for policy in noel_identity
            ),
        )

    oversized_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "X" * MANAGED_POLICY_CHARACTER_LIMIT,
                "Effect": "Allow",
                "Action": "sts:GetCallerIdentity",
                "Resource": "*",
            }
        ],
    }
    for label, limit, reserve, policy_class in (
        (
            "managedPolicyQuotaRejectsOverLimit",
            MANAGED_POLICY_CHARACTER_LIMIT,
            MANAGED_POLICY_CHARACTER_RESERVE,
            "managed policy",
        ),
        (
            "trustPolicyQuotaRejectsOverLimit",
            TRUST_POLICY_CHARACTER_LIMIT,
            TRUST_POLICY_CHARACTER_RESERVE,
            "trust policy",
        ),
    ):
        try:
            enforce_policy_character_reserve(
                {"overLimitMutation": oversized_policy},
                limit=limit,
                reserve=reserve,
                policy_class=policy_class,
            )
        except RuntimeError as error:
            record(
                label,
                f"Console IAM {policy_class} exhausted its required" in str(error),
            )
        else:
            record(label, False)

    state_bucket = "arn:aws:s3:::example-portfolio-111122223333-us-east-1-state"
    state_object = state_bucket + "/environments/manual/terraform.tfstate"
    lock_object = state_object + ".tflock"
    app_bucket = "arn:aws:s3:::example-portfolio-manual-documents"
    pass_context = {"iam:PassedToService": "ecs-tasks.amazonaws.com"}
    runtime_roles = [
        "task-execution",
        "web-workload",
        "api-workload",
        "ml-workload",
    ]
    for purpose in runtime_roles:
        role = f"arn:aws:iam::111122223333:role/example-portfolio-manual-{purpose}"
        record(
            f"identityCanPassExact{purpose}",
            policy_allows(permissions, "iam:PassRole", role, pass_context),
        )
        record(
            f"boundaryCanPassExact{purpose}",
            policy_allows(boundary, "iam:PassRole", role, pass_context),
        )

    forbidden_pass_roles = {
        "operator": "arn:aws:iam::111122223333:role/example-portfolio-manual-operator-deployment",
        "destroy": "arn:aws:iam::111122223333:role/example-portfolio-manual-destroy",
        "crossEnvironment": "arn:aws:iam::111122223333:role/example-portfolio-monthly-task-execution",
        "externalAccount": "arn:aws:iam::444455556666:role/example-portfolio-manual-task-execution",
        "synthesizedPurpose": "arn:aws:iam::111122223333:role/example-portfolio-manual-administrator",
    }
    for label, role in forbidden_pass_roles.items():
        record(
            f"identityCannotPass{label}",
            not policy_allows(permissions, "iam:PassRole", role, pass_context),
        )
        record(
            f"boundaryCannotPass{label}",
            not policy_allows(boundary, "iam:PassRole", role, pass_context),
        )
    exact_runtime_role = (
        "arn:aws:iam::111122223333:role/example-portfolio-manual-task-execution"
    )
    record(
        "identityCannotPassRuntimeToWrongService",
        not policy_allows(
            permissions,
            "iam:PassRole",
            exact_runtime_role,
            {"iam:PassedToService": "lambda.amazonaws.com"},
        ),
    )
    record(
        "boundaryCannotPassRuntimeToWrongService",
        not policy_allows(
            boundary,
            "iam:PassRole",
            exact_runtime_role,
            {"iam:PassedToService": "lambda.amazonaws.com"},
        ),
    )

    destroy_role = "arn:aws:iam::111122223333:role/example-portfolio-manual-destroy"
    record(
        "identityCanAssumeExactDestroyRole",
        policy_allows(permissions, "sts:AssumeRole", destroy_role),
    )
    record(
        "boundaryCanAssumeExactDestroyRole",
        policy_allows(boundary, "sts:AssumeRole", destroy_role),
    )
    for label, role in {
        "operator": forbidden_pass_roles["operator"],
        "crossEnvironment": "arn:aws:iam::111122223333:role/example-portfolio-monthly-destroy",
        "externalAccount": "arn:aws:iam::444455556666:role/example-portfolio-manual-destroy",
    }.items():
        record(
            f"identityCannotAssume{label}",
            not policy_allows(permissions, "sts:AssumeRole", role),
        )
        record(
            f"boundaryCannotAssume{label}",
            not policy_allows(boundary, "sts:AssumeRole", role),
        )

    for action in (
        "iam:AttachRolePolicy",
        "iam:CreatePolicyVersion",
        "iam:PutRolePolicy",
        "iam:SetDefaultPolicyVersion",
        "iam:UpdateAssumeRolePolicy",
    ):
        for label, policy in (
            ("operator", permissions),
            ("destroy", destroy),
            ("boundary", boundary),
        ):
            record(
                f"{label}Cannot{action.replace(':', '')}",
                not policy_allows(policy, action, destroy_role),
            )

    record(
        "identityCannotDeleteStateBucket",
        not policy_allows(permissions, "s3:DeleteBucket", state_bucket),
    )
    record(
        "boundaryCannotDeleteStateBucket",
        not policy_allows(boundary, "s3:DeleteBucket", state_bucket),
    )
    record(
        "identityCannotDeleteStateObject",
        not policy_allows(permissions, "s3:DeleteObject", state_object),
    )
    record(
        "boundaryCannotDeleteStateObject",
        not policy_allows(boundary, "s3:DeleteObject", state_object),
    )
    record(
        "identityCanDeleteLock",
        policy_allows(permissions, "s3:DeleteObject", lock_object),
    )
    record(
        "boundaryCanDeleteLock",
        policy_allows(boundary, "s3:DeleteObject", lock_object),
    )
    record(
        "boundaryHasIndependentSchedulerCeiling",
        policy_allows(boundary, "scheduler:CreateSchedule", "*")
        and not policy_allows(permissions, "scheduler:CreateSchedule", "*"),
    )

    owned_context = {
        f"aws:ResourceTag/{key}": value for key, value in OWNERSHIP_TAGS.items()
    }
    ownership_inverses: dict[str, dict[str, Any]] = {}
    for label, key, value in (
        ("crossEnvironment", "PortfolioEnvironment", "monthly"),
        ("crossRepository", "PortfolioRepository", "other/repository"),
        ("unmanaged", "PortfolioManaged", "false"),
        ("persistent", "PortfolioPersistent", "true"),
    ):
        inverse = dict(owned_context)
        inverse[f"aws:ResourceTag/{key}"] = value
        ownership_inverses[label] = inverse

    request_context = {
        f"aws:RequestTag/{key}": value for key, value in OWNERSHIP_TAGS.items()
    }
    request_context["aws:TagKeys"] = list(OWNERSHIP_TAGS)
    request_inverses: dict[str, dict[str, Any]] = {}
    for label, key, value in (
        ("crossEnvironment", "PortfolioEnvironment", "monthly"),
        ("crossRepository", "PortfolioRepository", "other/repository"),
        ("unmanaged", "PortfolioManaged", "false"),
        ("persistent", "PortfolioPersistent", "true"),
    ):
        inverse = dict(request_context)
        inverse["aws:TagKeys"] = list(OWNERSHIP_TAGS)
        inverse[f"aws:RequestTag/{key}"] = value
        request_inverses[label] = inverse
    missing_request_tag = dict(request_context)
    missing_request_tag.pop("aws:RequestTag/PortfolioRepository")
    missing_request_tag["aws:TagKeys"] = [
        key for key in OWNERSHIP_TAGS if key != "PortfolioRepository"
    ]
    request_inverses["missingOwnershipKey"] = missing_request_tag
    additional_request_tag = dict(request_context)
    additional_request_tag["aws:TagKeys"] = [*OWNERSHIP_TAGS, "Owner"]
    additional_request_tag["aws:RequestTag/Owner"] = "unexpected"
    request_inverses["additionalOwnershipKey"] = additional_request_tag

    def record_operator_denial(
        case_name: str,
        action: str,
        resource: str,
        context: dict[str, Any],
    ) -> None:
        identity_allows = policy_allows(permissions, action, resource, context)
        boundary_allows = policy_allows(boundary, action, resource, context)
        record(f"operatorIdentityRejects{case_name}", not identity_allows)
        record(
            f"operatorEffectiveRejects{case_name}",
            not (identity_allows and boundary_allows),
        )

    cloud_map_foreign_resources = {
        "Namespace": (
            "arn:aws:servicediscovery:us-east-1:111122223333:namespace/ns-foreign"
        ),
        "Service": (
            "arn:aws:servicediscovery:us-east-1:111122223333:service/srv-foreign"
        ),
    }
    cloud_map_retag_context = {
        f"aws:RequestTag/{key}": value for key, value in OWNERSHIP_TAGS.items()
    }
    cloud_map_retag_context["aws:TagKeys"] = list(OWNERSHIP_TAGS)
    cloud_map_tag_identity_statements = [
        statement
        for statement in permissions["Statement"]
        if "servicediscovery:TagResource" in string_values(statement.get("Action", []))
    ]
    expected_cloud_map_tag_condition = {
        "StringEquals": {
            f"aws:RequestTag/{key}": value for key, value in OWNERSHIP_TAGS.items()
        },
        "ForAllValues:StringEquals": {"aws:TagKeys": list(OWNERSHIP_TAGS)},
    }
    record(
        "operatorCloudMapTaggingUsesOneExactGlobalIdentityGrant",
        len(cloud_map_tag_identity_statements) == 1
        and cloud_map_tag_identity_statements[0].get("Resource") == "*"
        and cloud_map_tag_identity_statements[0].get("Condition")
        == expected_cloud_map_tag_condition,
    )
    cloud_map_tag_boundary_statements = [
        statement
        for statement in boundary["Statement"]
        if "servicediscovery:TagResource" in string_values(statement.get("Action", []))
    ]
    record(
        "operatorCloudMapTaggingUsesSeparateGlobalBoundaryCeiling",
        len(cloud_map_tag_boundary_statements) == 1
        and cloud_map_tag_boundary_statements[0].get("Resource") == "*"
        and "Condition" not in cloud_map_tag_boundary_statements[0],
    )
    for label, resource in cloud_map_foreign_resources.items():
        identity_allows = policy_allows(
            permissions,
            "servicediscovery:TagResource",
            resource,
            cloud_map_retag_context,
        )
        boundary_allows = policy_allows(
            boundary,
            "servicediscovery:TagResource",
            resource,
            cloud_map_retag_context,
        )
        record(
            f"operatorIdentityAllowsOwnerAcceptedForeignCloudMap{label}Retag",
            identity_allows,
        )
        record(
            f"operatorBoundaryAllowsOwnerAcceptedForeignCloudMap{label}Retag",
            boundary_allows,
        )
        record(
            f"operatorEffectiveAllowsOwnerAcceptedForeignCloudMap{label}Retag",
            identity_allows and boundary_allows,
        )

    for (
        resource_type,
        row_index,
        action,
        symbol,
        ownership,
        resource,
        context,
    ) in reviewed_operator_rows:
        case = "".join(part.title() for part in resource_type.split("_"))
        case += str(row_index)
        if ownership in {"resource-and-request-tags", "resource-tags"}:
            for inverse_label, inverse_tags in ownership_inverses.items():
                inverse_context = dict(context)
                inverse_context.update(inverse_tags)
                record_operator_denial(
                    f"{inverse_label.title()}{case}",
                    action,
                    resource,
                    inverse_context,
                )
        if ownership in {
            "exact-resource-and-request-tags",
            "owner-accepted-global-tagging",
            "request-tags",
            "resource-and-request-tags",
        } or any(key.startswith("aws:RequestTag/") for key in context):
            for inverse_label, inverse_tags in request_inverses.items():
                inverse_context = dict(context)
                for key in list(inverse_context):
                    if key.startswith("aws:RequestTag/") or key == "aws:TagKeys":
                        inverse_context.pop(key)
                inverse_context.update(inverse_tags)
                record_operator_denial(
                    f"{inverse_label.title()}{case}Request",
                    action,
                    resource,
                    inverse_context,
                )
        if ownership in {
            "exact-resource",
            "exact-resource-and-request-tags",
        } and not symbol.startswith("iam-"):
            record_operator_denial(
                f"ForeignResource{case}",
                action,
                foreign_operator_resource(symbol),
                context,
            )

    unrelated_secret = (
        "arn:aws:secretsmanager:us-east-1:111122223333:secret:unrelated-secret-abcdef"
    )
    for action in ("secretsmanager:GetSecretValue", "secretsmanager:PutSecretValue"):
        record_operator_denial(
            f"UnrelatedSecret{action.split(':', 1)[1]}",
            action,
            unrelated_secret,
            {},
        )
    cross_environment_security_group = dict(owned_context)
    cross_environment_security_group["aws:ResourceTag/PortfolioEnvironment"] = "monthly"
    for action in (
        "ec2:ModifySecurityGroupRules",
        "ec2:RevokeSecurityGroupEgress",
    ):
        record_operator_denial(
            f"CrossEnvironmentSecurityGroup{action.split(':', 1)[1]}",
            action,
            "arn:aws:ec2:us-east-1:111122223333:security-group/sg-foreign",
            cross_environment_security_group,
        )

    unconditioned_global_operator_writes: list[str] = []
    for statement in permissions["Statement"]:
        if statement.get("Condition") or statement.get("Resource") != "*":
            continue
        for action in string_values(statement.get("Action", [])):
            verb = action.split(":", 1)[-1].lower()
            if not verb.startswith(("describe", "get", "head", "list")):
                unconditioned_global_operator_writes.append(action)
    record(
        "operatorHasNoUnconditionedGlobalWrite",
        unconditioned_global_operator_writes == [],
    )

    generated_id_actions = [
        ("Vpc", "ec2:DeleteVpc", "arn:aws:ec2:us-east-1:111122223333:vpc/vpc-owned"),
        (
            "Subnet",
            "ec2:DeleteSubnet",
            "arn:aws:ec2:us-east-1:111122223333:subnet/subnet-owned",
        ),
        (
            "SecurityGroup",
            "ec2:DeleteSecurityGroup",
            "arn:aws:ec2:us-east-1:111122223333:security-group/sg-owned",
        ),
        (
            "SecurityGroupRule",
            "ec2:DeleteSecurityGroupRule",
            "arn:aws:ec2:us-east-1:111122223333:security-group-rule/sgr-owned",
        ),
        (
            "Route",
            "ec2:DeleteRoute",
            "arn:aws:ec2:us-east-1:111122223333:route-table/rtb-owned",
        ),
        (
            "RouteTable",
            "ec2:DeleteRouteTable",
            "arn:aws:ec2:us-east-1:111122223333:route-table/rtb-owned",
        ),
        (
            "InternetGateway",
            "ec2:DeleteInternetGateway",
            "arn:aws:ec2:us-east-1:111122223333:internet-gateway/igw-owned",
        ),
        (
            "VpcEndpoint",
            "ec2:DeleteVpcEndpoints",
            "arn:aws:ec2:us-east-1:111122223333:vpc-endpoint/vpce-owned",
        ),
        (
            "DetachInternetGateway",
            "ec2:DetachInternetGateway",
            "arn:aws:ec2:us-east-1:111122223333:internet-gateway/igw-owned",
        ),
        (
            "DetachInternetGatewayVpc",
            "ec2:DetachInternetGateway",
            "arn:aws:ec2:us-east-1:111122223333:vpc/vpc-owned",
        ),
        (
            "DisassociateRouteTable",
            "ec2:DisassociateRouteTable",
            "arn:aws:ec2:us-east-1:111122223333:route-table/rtb-owned",
        ),
        (
            "DisassociateRouteTableSubnet",
            "ec2:DisassociateRouteTable",
            "arn:aws:ec2:us-east-1:111122223333:subnet/subnet-owned",
        ),
        (
            "RevokeSecurityGroupEgress",
            "ec2:RevokeSecurityGroupEgress",
            "arn:aws:ec2:us-east-1:111122223333:security-group/sg-owned",
        ),
        (
            "RevokeSecurityGroupIngress",
            "ec2:RevokeSecurityGroupIngress",
            "arn:aws:ec2:us-east-1:111122223333:security-group/sg-owned",
        ),
        (
            "HttpApi",
            "apigateway:DELETE",
            "arn:aws:apigateway:us-east-1::/apis/api-owned",
        ),
        (
            "HttpApiIntegration",
            "apigateway:DELETE",
            "arn:aws:apigateway:us-east-1::/apis/api-owned/integrations/int-owned",
        ),
        (
            "HttpApiRoute",
            "apigateway:DELETE",
            "arn:aws:apigateway:us-east-1::/apis/api-owned/routes/route-owned",
        ),
        (
            "HttpApiStage",
            "apigateway:DELETE",
            "arn:aws:apigateway:us-east-1::/apis/api-owned/stages/$default",
        ),
        (
            "VpcLink",
            "apigateway:DELETE",
            "arn:aws:apigateway:us-east-1::/vpclinks/vpclink-owned",
        ),
        (
            "CognitoGroup",
            "cognito-idp:DeleteGroup",
            "arn:aws:cognito-idp:us-east-1:111122223333:userpool/us-east-1_owned",
        ),
        (
            "CognitoBranding",
            "cognito-idp:DeleteManagedLoginBranding",
            "arn:aws:cognito-idp:us-east-1:111122223333:userpool/us-east-1_owned",
        ),
        (
            "CognitoResourceServer",
            "cognito-idp:DeleteResourceServer",
            "arn:aws:cognito-idp:us-east-1:111122223333:userpool/us-east-1_owned",
        ),
        (
            "CognitoUserPool",
            "cognito-idp:DeleteUserPool",
            "arn:aws:cognito-idp:us-east-1:111122223333:userpool/us-east-1_owned",
        ),
        (
            "CognitoClient",
            "cognito-idp:DeleteUserPoolClient",
            "arn:aws:cognito-idp:us-east-1:111122223333:userpool/us-east-1_owned",
        ),
        (
            "CognitoDomain",
            "cognito-idp:DeleteUserPoolDomain",
            "arn:aws:cognito-idp:us-east-1:111122223333:userpool/us-east-1_owned",
        ),
        (
            "CloudMapNamespace",
            "servicediscovery:DeleteNamespace",
            "arn:aws:servicediscovery:us-east-1:111122223333:namespace/ns-owned",
        ),
        (
            "CloudMapService",
            "servicediscovery:DeleteService",
            "arn:aws:servicediscovery:us-east-1:111122223333:service/srv-owned",
        ),
    ]
    for label, action, resource in generated_id_actions:
        record(
            f"destroyAllowsOwned{label}",
            policy_allows(destroy, action, resource, owned_context),
        )
        record(
            f"boundaryAllowsOwned{label}",
            policy_allows(boundary, action, resource, owned_context),
        )
        for inverse_label, inverse_context in ownership_inverses.items():
            record(
                f"destroyRejects{inverse_label}{label}",
                not policy_allows(destroy, action, resource, inverse_context),
            )

    exact_name_actions = [
        (
            "EcsCluster",
            "ecs:DeleteCluster",
            "arn:aws:ecs:us-east-1:111122223333:cluster/example-portfolio-manual",
            "arn:aws:ecs:us-east-1:111122223333:cluster/example-portfolio-monthly",
            {},
        ),
        (
            "EcsServiceDelete",
            "ecs:DeleteService",
            "arn:aws:ecs:us-east-1:111122223333:service/example-portfolio-manual/example-portfolio-manual-web",
            "arn:aws:ecs:us-east-1:111122223333:service/example-portfolio-monthly/example-portfolio-monthly-web",
            {},
        ),
        (
            "EcsServiceUpdate",
            "ecs:UpdateService",
            "arn:aws:ecs:us-east-1:111122223333:service/example-portfolio-manual/example-portfolio-manual-api",
            "arn:aws:ecs:us-east-1:111122223333:service/example-portfolio-monthly/example-portfolio-monthly-api",
            {},
        ),
        (
            "LogGroup",
            "logs:DeleteLogGroup",
            "arn:aws:logs:us-east-1:111122223333:log-group:/portfolio/example-portfolio/manual/web",
            "arn:aws:logs:us-east-1:111122223333:log-group:/portfolio/example-portfolio/monthly/web",
            owned_context,
        ),
        (
            "MqBroker",
            "mq:DeleteBroker",
            "arn:aws:mq:us-east-1:111122223333:broker:example-portfolio-manual-rabbitmq:broker-id",
            "arn:aws:mq:us-east-1:111122223333:broker:example-portfolio-monthly-rabbitmq:broker-id",
            owned_context,
        ),
        (
            "RdsInstance",
            "rds:DeleteDBInstance",
            "arn:aws:rds:us-east-1:111122223333:db:example-portfolio-manual-postgresql",
            "arn:aws:rds:us-east-1:111122223333:db:example-portfolio-monthly-postgresql",
            owned_context,
        ),
        (
            "RdsSubnetGroup",
            "rds:DeleteDBSubnetGroup",
            "arn:aws:rds:us-east-1:111122223333:subgrp:example-portfolio-manual",
            "arn:aws:rds:us-east-1:111122223333:subgrp:example-portfolio-monthly",
            owned_context,
        ),
        (
            "Secret",
            "secretsmanager:DeleteSecret",
            "arn:aws:secretsmanager:us-east-1:111122223333:secret:example-portfolio-manual-database-abcdef",
            "arn:aws:secretsmanager:us-east-1:111122223333:secret:example-portfolio-monthly-database-abcdef",
            owned_context,
        ),
        (
            "ApplicationBucket",
            "s3:DeleteBucket",
            app_bucket,
            "arn:aws:s3:::example-portfolio-monthly-documents",
            {},
        ),
        (
            "ApplicationObject",
            "s3:DeleteObject",
            app_bucket + "/object",
            "arn:aws:s3:::example-portfolio-monthly-documents/object",
            {},
        ),
    ]
    for label, action, owned_resource, foreign_resource, context in exact_name_actions:
        record(
            f"destroyAllowsExact{label}",
            policy_allows(destroy, action, owned_resource, context),
        )
        record(
            f"boundaryAllowsExact{label}",
            policy_allows(boundary, action, owned_resource, context),
        )
        record(
            f"destroyRejectsForeign{label}",
            not policy_allows(destroy, action, foreign_resource, context),
        )

    cloud_map_via = {"aws:CalledVia": ["servicediscovery.amazonaws.com"]}
    mq_via = {"aws:CalledVia": ["mq.amazonaws.com"]}
    wrong_via = {"aws:CalledVia": ["cloudformation.amazonaws.com"]}
    hosted_zone = "arn:aws:route53:::hostedzone/owned-zone"
    for action, resource in (
        ("ec2:DescribeRegions", "*"),
        ("route53:CreateHostedZone", "*"),
        ("route53:GetHostedZone", hosted_zone),
        ("route53:ListHostedZonesByName", "*"),
    ):
        label = action.split(":", 1)[1]
        record(
            f"operatorAllowsCloudMap{label}",
            policy_allows(permissions, action, resource, cloud_map_via),
        )
        record(
            f"operatorRejectsDirect{label}",
            not policy_allows(permissions, action, resource),
        )
        record(
            f"operatorRejectsWrongService{label}",
            not policy_allows(permissions, action, resource, wrong_via),
        )
        record(
            f"boundaryAllowsCloudMap{label}",
            policy_allows(boundary, action, resource, cloud_map_via),
        )
    for label, policy in (
        ("operator", permissions),
        ("destroy", destroy),
        ("boundary", boundary),
    ):
        record(
            f"{label}CannotDeleteHostedZone",
            not policy_allows(
                policy, "route53:DeleteHostedZone", hosted_zone, cloud_map_via
            ),
        )

    network_interface = "arn:aws:ec2:us-east-1:111122223333:network-interface/eni-owned"
    for action, dependent_resource in (
        ("ec2:DeleteNetworkInterface", network_interface),
        (
            "ec2:DeleteNetworkInterfacePermission",
            "arn:aws:ec2:us-east-1:111122223333:network-interface-permission/enip-owned",
        ),
        (
            "ec2:DeleteVpcEndpoints",
            "arn:aws:ec2:us-east-1:111122223333:vpc-endpoint/vpce-owned",
        ),
        ("ec2:DetachNetworkInterface", network_interface),
    ):
        label = action.split(":", 1)[1]
        record(
            f"destroyAllowsMq{label}",
            policy_allows(destroy, action, dependent_resource, mq_via),
        )
        record(
            f"destroyRejectsDirect{label}",
            not policy_allows(destroy, action, dependent_resource),
        )
        record(
            f"destroyRejectsWrongService{label}",
            not policy_allows(destroy, action, dependent_resource, cloud_map_via),
        )
        record(
            f"operatorRejects{label}",
            not policy_allows(permissions, action, dependent_resource, mq_via),
        )
        record(
            f"boundaryAllowsMq{label}",
            policy_allows(boundary, action, dependent_resource, mq_via),
        )
    record(
        "destroyCanReadNetworkInterfaceCleanupState",
        policy_allows(destroy, "ec2:DescribeNetworkInterfaces", "*"),
    )
    record(
        "operatorCannotReadNetworkInterfaceCleanupState",
        not policy_allows(permissions, "ec2:DescribeNetworkInterfaces", "*"),
    )

    unconditioned_global_writes: list[str] = []
    for statement in destroy["Statement"]:
        if statement.get("Condition") or statement.get("Resource") != "*":
            continue
        for action in string_values(statement.get("Action", [])):
            verb = action.split(":", 1)[-1].lower()
            if not verb.startswith(("describe", "get", "head", "list")):
                unconditioned_global_writes.append(action)
    record(
        "onlyAwsGlobalDestroyActionIsTaskDefinitionDeregister",
        unconditioned_global_writes == ["ecs:DeregisterTaskDefinition"],
    )
    record(
        "destroyCanDeregisterTaskDefinition",
        policy_allows(
            destroy,
            "ecs:DeregisterTaskDefinition",
            "arn:aws:ecs:us-east-1:111122223333:task-definition/example-portfolio-manual-web:1",
        ),
    )
    record(
        "operatorCannotDeregisterTaskDefinition",
        not policy_allows(
            permissions,
            "ecs:DeregisterTaskDefinition",
            "arn:aws:ecs:us-east-1:111122223333:task-definition/example-portfolio-manual-web:1",
        ),
    )

    failed = [name for name, passed in invariant_cases.items() if not passed]
    if failed:
        raise RuntimeError(f"Console IAM invariant failed: {failed}")

    documents = sorted(
        [CONSOLE_IAM_ROOT / "manifest.json"]
        + [CONSOLE_IAM_ROOT / spec["document"] for spec in policy_specs.values()]
        + [CONSOLE_IAM_ROOT / trust for trust in trust_files]
    )
    digest = hashlib.sha256()
    for path in documents:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return {
        "managedPolicies": len(policies),
        "serviceLinkedRoles": len(expected_service_linked_roles),
        "roles": len(roles),
        "trustPolicies": len(trust_files),
        "operatorActionRows": rows,
        "allowedLayerDecisions": allowed_layer_decisions,
        "invariantCases": len(invariant_cases),
        "managedPolicyCharacterLimit": MANAGED_POLICY_CHARACTER_LIMIT,
        "managedPolicyCharacterReserve": MANAGED_POLICY_CHARACTER_RESERVE,
        "managedPolicyCharacterSizes": managed_policy_sizes,
        "trustPolicyCharacterLimit": TRUST_POLICY_CHARACTER_LIMIT,
        "trustPolicyCharacterReserve": TRUST_POLICY_CHARACTER_RESERVE,
        "trustPolicyCharacterSizes": trust_policy_sizes,
        "unconditionedGlobalOperatorWrites": unconditioned_global_operator_writes,
        "unconditionedGlobalDestroyActions": unconditioned_global_writes,
        "sha256": digest.hexdigest(),
    }


def verify_operator_action_matrix() -> dict[str, Any]:
    matrix = json.loads(OPERATOR_ACTION_MATRIX_PATH.read_text(encoding="utf-8"))
    if not isinstance(matrix, dict) or type(matrix.get("schemaVersion")) is not int:
        raise RuntimeError("Operator action matrix must use an integer schema")
    if matrix["schemaVersion"] != 1:
        raise RuntimeError("Unknown operator action matrix schema")
    provider = matrix.get("terraformAwsProvider")
    expected_provider = {
        "source": "hashicorp/aws",
        "version": "6.58.0",
        "sourceCommit": "9f8360a9295ffe4507e06d943a3b8c673a781ced",
    }
    if provider != expected_provider:
        raise RuntimeError(
            "Operator action matrix must name the exact reviewed AWS provider: "
            f"expected={expected_provider}, actual={provider}"
        )
    resource_actions = matrix.get("resourceActions")
    if not isinstance(resource_actions, dict):
        raise RuntimeError("Operator action matrix resourceActions must be an object")
    expected_types = {
        resource_type
        for resource_type in EXPECTED_RESOURCE_COUNTS
        if resource_type.startswith("aws_")
    }
    if set(resource_actions) != expected_types:
        raise RuntimeError(
            "Operator action matrix must exactly cover the planned AWS resource types: "
            f"missing={sorted(expected_types - set(resource_actions))}, "
            f"extra={sorted(set(resource_actions) - expected_types)}"
        )

    rows: list[str] = []
    for resource_type, actions in sorted(resource_actions.items()):
        if not isinstance(actions, list) or not actions:
            raise RuntimeError(f"Operator action list is empty: {resource_type}")
        for row in actions:
            if not isinstance(row, list) or len(row) not in {3, 4}:
                raise RuntimeError(
                    f"Invalid operator action row for {resource_type}: {row}"
                )
            action, resource, ownership = row[:3]
            if not all(isinstance(value, str) and value for value in row[:3]):
                raise RuntimeError(f"Operator action row has a non-string field: {row}")
            if ":" not in action or resource == "":
                raise RuntimeError(
                    f"Operator action row has an invalid action/resource: {row}"
                )
            if ownership not in OPERATOR_ACTION_OWNERSHIP_MODES:
                raise RuntimeError(f"Unknown operator action ownership mode: {row}")
            if ownership == "global-read":
                verb = action.split(":", 1)[1].lower()
                if not verb.startswith(("describe", "get", "head", "list")):
                    raise RuntimeError(
                        f"Global operator action must be read-only: {row}"
                    )
            if (
                ownership
                in {
                    "exact-resource",
                    "exact-resource-and-request-tags",
                    "resource-and-request-tags",
                    "resource-tags",
                }
                and resource == "*"
            ):
                raise RuntimeError(
                    f"Resource-bound operator action cannot use Resource '*': {row}"
                )
            if ownership == "service-delegated" and (
                action not in CLOUD_MAP_DELEGATED_ACTIONS
            ):
                raise RuntimeError(f"Unexpected service-delegated action: {row}")
            if ownership == "owner-accepted-global-tagging" and (
                action != "servicediscovery:TagResource"
                or resource not in {"cloudmap-namespace", "cloudmap-service"}
            ):
                raise RuntimeError(
                    "Owner-accepted global tagging is limited to the two exact "
                    f"Cloud Map authorization targets: {row}"
                )
            if action == "servicediscovery:TagResource" and (
                ownership != "owner-accepted-global-tagging"
            ):
                raise RuntimeError(
                    "Cloud Map TagResource must disclose its owner-accepted "
                    f"global-target limitation: {row}"
                )
            if len(row) == 4 and not isinstance(row[3], dict):
                raise RuntimeError(f"Operator action context must be an object: {row}")
            if ownership == "service-delegated" and (
                len(row) != 4
                or row[3] != {"aws:CalledVia": ["servicediscovery.amazonaws.com"]}
            ):
                raise RuntimeError(
                    "Service-delegated action must use the exact Cloud Map "
                    f"forward-access context: {row}"
                )
            rows.append(json.dumps([resource_type, *row], sort_keys=True))
    if len(rows) != len(set(rows)):
        raise RuntimeError(
            "Operator action matrix contains duplicate resource/action rows"
        )
    required_cloud_map_authorizations = {
        "aws_service_discovery_private_dns_namespace": {
            (
                "servicediscovery:CreatePrivateDnsNamespace",
                "*",
                "request-tags",
            ),
            (
                "servicediscovery:TagResource",
                "cloudmap-namespace",
                "owner-accepted-global-tagging",
            ),
        },
        "aws_service_discovery_service": {
            (
                "servicediscovery:CreateService",
                "cloudmap-service",
                "request-tags",
            ),
            (
                "servicediscovery:TagResource",
                "cloudmap-service",
                "owner-accepted-global-tagging",
            ),
        },
    }

    def require_cloud_map_operation_authorizations(
        candidate_actions: dict[str, Any],
    ) -> None:
        for resource_type, required in required_cloud_map_authorizations.items():
            actual = {tuple(row[:3]) for row in candidate_actions[resource_type]}
            if not required.issubset(actual):
                raise RuntimeError(
                    "Cloud Map create operations must include every action from "
                    "AWS's operation-to-IAM authorization mapping: "
                    f"{resource_type} missing={sorted(required - actual)}"
                )

    require_cloud_map_operation_authorizations(resource_actions)
    operation_mapping_mutation_cases = 0
    for resource_type in required_cloud_map_authorizations:
        mutation = {key: list(value) for key, value in resource_actions.items()}
        mutation[resource_type] = [
            row
            for row in mutation[resource_type]
            if row[0] != "servicediscovery:TagResource"
        ]
        try:
            require_cloud_map_operation_authorizations(mutation)
        except RuntimeError as error:
            if resource_type not in str(error):
                raise RuntimeError(
                    "Cloud Map operation-mapping mutation failed unexpectedly"
                ) from error
            operation_mapping_mutation_cases += 1
        else:
            raise RuntimeError(
                "Cloud Map operation-mapping mutation was not rejected: "
                f"{resource_type}"
            )
    return {
        "provider": provider,
        "resourceTypes": len(resource_actions),
        "actionRows": len(rows),
        "operationMappingMutationCases": operation_mapping_mutation_cases,
        "sha256": hashlib.sha256(OPERATOR_ACTION_MATRIX_PATH.read_bytes()).hexdigest(),
    }


def require_command(name: str) -> str:
    resolved = shutil.which(name)
    if resolved is None:
        raise RuntimeError(f"Required command is not available: {name}")
    return resolved


def run(label: str, command: list[str]) -> None:
    print(f"\n==> {label}", flush=True)
    subprocess.run(command, cwd=REPOSITORY_ROOT, check=True)


def command_version(command: str, argument: str) -> str:
    completed = subprocess.run(
        [command, argument], text=True, capture_output=True, check=True
    )
    return completed.stdout.splitlines()[0].strip()


def source_head() -> str:
    configured = os.environ.get("PORTFOLIO_VERIFICATION_HEAD_SHA", "").strip()
    if configured:
        if len(configured) != 40 or any(
            character not in "0123456789abcdef" for character in configured
        ):
            raise RuntimeError(
                "PORTFOLIO_VERIFICATION_HEAD_SHA must be a full lowercase SHA"
            )
        return configured
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return completed.stdout.strip()


def walk_resources(module: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield from module.get("resources", [])
    for child in module.get("child_modules", []):
        yield from walk_resources(child)


def resource_by_address(
    resources: list[dict[str, Any]], address: str
) -> dict[str, Any]:
    for resource in resources:
        if resource["address"] == address:
            return resource
    raise RuntimeError(f"Sanitized plan is missing resource: {address}")


def create_sanitized_plan(terraform: str, plan_path: Path) -> dict[str, Any]:
    environment = os.environ.copy()
    environment.update(
        {
            "AWS_ACCESS_KEY_ID": "synthetic-plan-identity",
            "AWS_SECRET_ACCESS_KEY": "synthetic-plan-value-not-a-secret",
            "AWS_EC2_METADATA_DISABLED": "true",
            # Any unexpected provider call fails closed instead of reaching AWS.
            "AWS_ENDPOINT_URL": "http://127.0.0.1:9",
        }
    )
    command = [
        terraform,
        f"-chdir={ENVIRONMENT_ROOT}",
        "plan",
        "-refresh=false",
        "-input=false",
        "-lock=false",
        "-no-color",
        f"-var-file={TFVARS_PATH}",
        f"-out={plan_path}",
    ]
    completed = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "AWS-free Terraform plan failed closed; provider diagnostics are "
            "intentionally omitted from public evidence"
        )
    show = subprocess.run(
        [terraform, f"-chdir={ENVIRONMENT_ROOT}", "show", "-json", str(plan_path)],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(show.stdout)


def verify_resource_inventory(plan: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    resources = list(walk_resources(plan["planned_values"]["root_module"]))
    counts = Counter(resource["type"] for resource in resources)
    if dict(sorted(counts.items())) != EXPECTED_RESOURCE_COUNTS:
        raise RuntimeError(
            "Planned resource inventory changed: "
            f"expected={EXPECTED_RESOURCE_COUNTS}, actual={dict(sorted(counts.items()))}"
        )
    present_forbidden = sorted(FORBIDDEN_RESOURCE_TYPES & counts.keys())
    if present_forbidden:
        raise RuntimeError(f"Forbidden resource types planned: {present_forbidden}")
    for change in plan["resource_changes"]:
        if change["change"]["actions"] != ["create"]:
            raise RuntimeError(
                f"Static fixture must only create fresh state: {change['address']}"
            )
    return resources, len(resources)


def verify_tags(resources: list[dict[str, Any]]) -> int:
    tagged = 0
    for resource in resources:
        tags = resource["values"].get("tags_all")
        if tags is None:
            continue
        if tags != OWNERSHIP_TAGS:
            raise RuntimeError(
                f"Resource has non-exact ownership tags: {resource['address']} {tags}"
            )
        tagged += 1
    if tagged != 60:
        raise RuntimeError(f"Expected 60 taggable resources, got {tagged}")
    return tagged


def nested_value(value: Any, path: tuple[str | int, ...]) -> Any:
    for segment in path:
        value = value[segment]
    return value


def verify_planned_service_properties(resources: list[dict[str, Any]]) -> int:
    checks: list[tuple[str, bool]] = []

    def expect(
        address: str,
        path: tuple[str | int, ...],
        expected: Any,
    ) -> None:
        resource = resource_by_address(resources, address)
        try:
            actual = nested_value(resource["values"], path)
        except (KeyError, IndexError, TypeError) as error:
            rendered_path = ".".join(str(segment) for segment in path)
            raise RuntimeError(
                f"Planned value is missing: {address}.{rendered_path}"
            ) from error
        rendered_path = ".".join(str(segment) for segment in path)
        checks.append((f"{address}.{rendered_path}", actual == expected))

    expect("module.network.aws_vpc.environment", ("cidr_block",), "10.42.0.0/16")
    expect("module.network.aws_vpc.environment", ("enable_dns_support",), True)
    expect("module.network.aws_vpc.environment", ("enable_dns_hostnames",), True)
    for index, cidr in enumerate(("10.42.0.0/24", "10.42.1.0/24")):
        address = f'module.network.aws_subnet.public_task["{index}"]'
        expect(address, ("cidr_block",), cidr)
        expect(address, ("map_public_ip_on_launch",), False)
    for index, cidr in enumerate(("10.42.10.0/24", "10.42.11.0/24")):
        address = f'module.network.aws_subnet.isolated_service["{index}"]'
        expect(address, ("cidr_block",), cidr)
        expect(address, ("map_public_ip_on_launch",), False)
    expect(
        "module.network.aws_route.public_internet",
        ("destination_cidr_block",),
        "0.0.0.0/0",
    )
    expect("module.network.aws_vpc_endpoint.s3", ("vpc_endpoint_type",), "Gateway")
    expect(
        "module.network.aws_vpc_endpoint.s3",
        ("service_name",),
        "com.amazonaws.us-east-1.s3",
    )

    expect("module.ingress.aws_apigatewayv2_api.web", ("protocol_type",), "HTTP")
    expect(
        "module.ingress.aws_apigatewayv2_api.web",
        ("disable_execute_api_endpoint",),
        False,
    )
    expect(
        "module.ingress.aws_apigatewayv2_integration.web",
        ("integration_type",),
        "HTTP_PROXY",
    )
    expect(
        "module.ingress.aws_apigatewayv2_integration.web",
        ("connection_type",),
        "VPC_LINK",
    )
    expect("module.ingress.aws_apigatewayv2_route.default", ("route_key",), "$default")
    expect(
        "module.ingress.aws_apigatewayv2_route.default",
        ("authorization_type",),
        "NONE",
    )
    expect("module.ingress.aws_apigatewayv2_stage.default", ("auto_deploy",), True)
    expect(
        "module.ingress.aws_apigatewayv2_stage.default",
        ("default_route_settings", 0, "throttling_burst_limit"),
        20,
    )
    expect(
        "module.ingress.aws_apigatewayv2_stage.default",
        ("default_route_settings", 0, "throttling_rate_limit"),
        10,
    )

    task_contracts = {
        "web": ("256", "512", "web-workload"),
        "api": ("512", "1024", "api-workload"),
        "migration": ("512", "1024", "api-workload"),
        "ml": ("1024", "2048", "ml-workload"),
    }
    execution_role = (
        "arn:aws:iam::111122223333:role/example-portfolio-manual-task-execution"
    )
    for name, (cpu, memory, workload) in task_contracts.items():
        address = f"module.runtime.aws_ecs_task_definition.{name}"
        expect(address, ("network_mode",), "awsvpc")
        expect(address, ("requires_compatibilities",), ["FARGATE"])
        expect(address, ("cpu",), cpu)
        expect(address, ("memory",), memory)
        expect(address, ("execution_role_arn",), execution_role)
        expect(
            address,
            ("task_role_arn",),
            f"arn:aws:iam::111122223333:role/example-portfolio-manual-{workload}",
        )
        expect(address, ("runtime_platform", 0, "cpu_architecture"), "X86_64")
        expect(
            address,
            ("runtime_platform", 0, "operating_system_family"),
            "LINUX",
        )

    service_addresses = (
        'module.runtime.aws_ecs_service.application["web"]',
        'module.runtime.aws_ecs_service.application["api"]',
        "module.runtime.aws_ecs_service.ml",
    )
    for address in service_addresses:
        expect(address, ("launch_type",), "FARGATE")
        expect(address, ("platform_version",), "1.4.0")
        expect(address, ("desired_count",), 1)
        expect(address, ("network_configuration", 0, "assign_public_ip"), True)
        expect(address, ("load_balancer",), [])
        expect(address, ("deployment_circuit_breaker", 0, "enable"), True)
        expect(address, ("deployment_circuit_breaker", 0, "rollback"), True)

    database = "module.managed_state.aws_db_instance.postgresql"
    for path, expected in (
        (("engine",), "postgres"),
        (("engine_version",), "18"),
        (("instance_class",), "db.t4g.micro"),
        (("allocated_storage",), 20),
        (("storage_type",), "gp3"),
        (("storage_encrypted",), True),
        (("multi_az",), False),
        (("publicly_accessible",), False),
        (("backup_retention_period",), 0),
        (("deletion_protection",), False),
        (("delete_automated_backups",), True),
        (("skip_final_snapshot",), True),
    ):
        expect(database, path, expected)

    broker = "module.managed_state.aws_mq_broker.rabbitmq"
    for path, expected in (
        (("engine_type",), "RabbitMQ"),
        (("engine_version",), "4.2"),
        (("host_instance_type",), "mq.m7g.large"),
        (("deployment_mode",), "SINGLE_INSTANCE"),
        (("storage_type",), "ebs"),
        (("authentication_strategy",), "simple"),
        (("publicly_accessible",), False),
        (("encryption_options", 0, "use_aws_owned_key"), True),
        (("user", 0, "console_access"), False),
    ):
        expect(broker, path, expected)

    bucket = "module.managed_state.aws_s3_bucket.application"
    expect(bucket, ("force_destroy",), True)
    public_block = "module.managed_state.aws_s3_bucket_public_access_block.application"
    for field in (
        "block_public_acls",
        "block_public_policy",
        "ignore_public_acls",
        "restrict_public_buckets",
    ):
        expect(public_block, (field,), True)
    expect(
        "module.managed_state.aws_s3_bucket_server_side_encryption_configuration.application",
        ("rule", 0, "apply_server_side_encryption_by_default", 0, "sse_algorithm"),
        "AES256",
    )
    lifecycle = "module.managed_state.aws_s3_bucket_lifecycle_configuration.application"
    expect(lifecycle, ("rule", 0, "status"), "Enabled")
    expect(lifecycle, ("rule", 0, "expiration", 0, "days"), 2)
    expect(
        lifecycle,
        ("rule", 0, "abort_incomplete_multipart_upload", 0, "days_after_initiation"),
        1,
    )
    policy = json.loads(
        resource_by_address(
            resources, "module.managed_state.aws_s3_bucket_policy.application"
        )["values"]["policy"]
    )
    checks.append(
        (
            "application bucket denies insecure transport",
            policy["Statement"]
            == [
                {
                    "Action": "s3:*",
                    "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                    "Effect": "Deny",
                    "Principal": "*",
                    "Resource": [
                        "arn:aws:s3:::example-portfolio-manual-documents",
                        "arn:aws:s3:::example-portfolio-manual-documents/*",
                    ],
                    "Sid": "DenyInsecureTransport",
                }
            ],
        )
    )

    for name in ("database", "broker"):
        expect(
            f"module.managed_state.aws_secretsmanager_secret.{name}",
            ("recovery_window_in_days",),
            0,
        )

    user_pool = "module.identity.aws_cognito_user_pool.environment"
    expect(
        user_pool, ("admin_create_user_config", 0, "allow_admin_create_user_only"), True
    )
    expect(user_pool, ("deletion_protection",), "INACTIVE")
    expect(user_pool, ("mfa_configuration",), "OFF")
    client = "module.identity.aws_cognito_user_pool_client.web"
    expect(client, ("generate_secret",), False)
    expect(client, ("allowed_oauth_flows_user_pool_client",), True)
    expect(client, ("allowed_oauth_flows",), ["code"])
    expect(client, ("supported_identity_providers",), ["COGNITO"])
    expect(
        "module.identity.aws_cognito_user_pool_domain.environment",
        ("managed_login_version",),
        2,
    )
    expect(
        "module.identity.aws_cognito_managed_login_branding.web",
        ("use_cognito_provided_values",),
        True,
    )

    log_groups = [
        resource
        for resource in resources
        if resource["type"] == "aws_cloudwatch_log_group"
    ]
    checks.append(("five bounded environment log groups", len(log_groups) == 5))
    checks.append(
        (
            "all log groups use three-day retention",
            all(
                resource["values"]["retention_in_days"] == 3 for resource in log_groups
            ),
        )
    )
    checks.append(
        (
            "all log groups remain environment-owned",
            all(
                resource["values"]["name"].startswith(
                    "/portfolio/example-portfolio/manual/"
                )
                for resource in log_groups
            ),
        )
    )

    failures = [description for description, result in checks if not result]
    if failures:
        raise RuntimeError(f"Planned service property assertions failed: {failures}")
    return len(checks)


def verify_security_group_reference_contract(
    plan: dict[str, Any], resources: list[dict[str, Any]]
) -> int:
    network = plan["configuration"]["root_module"]["module_calls"]["network"]["module"]
    configured_rules = {
        resource["address"]: resource
        for resource in network["resources"]
        if resource["type"]
        in {
            "aws_vpc_security_group_egress_rule",
            "aws_vpc_security_group_ingress_rule",
        }
    }
    dynamic_group_reference = {"aws_security_group.environment", "each.key"}
    expected_references = {
        "aws_vpc_security_group_egress_rule.api_to_database": {
            "security_group_id": {
                'aws_security_group.environment["api"].id',
                'aws_security_group.environment["api"]',
                "aws_security_group.environment",
            },
            "referenced_security_group_id": {
                'aws_security_group.environment["database"].id',
                'aws_security_group.environment["database"]',
                "aws_security_group.environment",
            },
        },
        "aws_vpc_security_group_egress_rule.broker_clients": {
            "security_group_id": dynamic_group_reference,
            "referenced_security_group_id": {
                'aws_security_group.environment["broker"].id',
                'aws_security_group.environment["broker"]',
                "aws_security_group.environment",
            },
        },
        "aws_vpc_security_group_egress_rule.task_dns_tcp": {
            "security_group_id": dynamic_group_reference,
        },
        "aws_vpc_security_group_egress_rule.task_dns_udp": {
            "security_group_id": dynamic_group_reference,
        },
        "aws_vpc_security_group_egress_rule.task_https": {
            "security_group_id": dynamic_group_reference,
        },
        "aws_vpc_security_group_egress_rule.vpc_link_to_web": {
            "security_group_id": {
                'aws_security_group.environment["vpc-link"].id',
                'aws_security_group.environment["vpc-link"]',
                "aws_security_group.environment",
            },
            "referenced_security_group_id": {
                'aws_security_group.environment["web"].id',
                'aws_security_group.environment["web"]',
                "aws_security_group.environment",
            },
        },
        "aws_vpc_security_group_egress_rule.web_to_api": {
            "security_group_id": {
                'aws_security_group.environment["web"].id',
                'aws_security_group.environment["web"]',
                "aws_security_group.environment",
            },
            "referenced_security_group_id": {
                'aws_security_group.environment["api"].id',
                'aws_security_group.environment["api"]',
                "aws_security_group.environment",
            },
        },
        "aws_vpc_security_group_ingress_rule.api_from_web": {
            "security_group_id": {
                'aws_security_group.environment["api"].id',
                'aws_security_group.environment["api"]',
                "aws_security_group.environment",
            },
            "referenced_security_group_id": {
                'aws_security_group.environment["web"].id',
                'aws_security_group.environment["web"]',
                "aws_security_group.environment",
            },
        },
        "aws_vpc_security_group_ingress_rule.broker_from_clients": {
            "security_group_id": {
                'aws_security_group.environment["broker"].id',
                'aws_security_group.environment["broker"]',
                "aws_security_group.environment",
            },
            "referenced_security_group_id": dynamic_group_reference,
        },
        "aws_vpc_security_group_ingress_rule.database_from_api": {
            "security_group_id": {
                'aws_security_group.environment["database"].id',
                'aws_security_group.environment["database"]',
                "aws_security_group.environment",
            },
            "referenced_security_group_id": {
                'aws_security_group.environment["api"].id',
                'aws_security_group.environment["api"]',
                "aws_security_group.environment",
            },
        },
        "aws_vpc_security_group_ingress_rule.web_from_vpc_link": {
            "security_group_id": {
                'aws_security_group.environment["web"].id',
                'aws_security_group.environment["web"]',
                "aws_security_group.environment",
            },
            "referenced_security_group_id": {
                'aws_security_group.environment["vpc-link"].id',
                'aws_security_group.environment["vpc-link"]',
                "aws_security_group.environment",
            },
        },
    }
    if set(configured_rules) != set(expected_references):
        raise RuntimeError(
            "Security Group rule configuration inventory drifted: "
            f"actual={sorted(configured_rules)}"
        )

    assertion_count = 1
    for address, expected_fields in expected_references.items():
        expressions = configured_rules[address]["expressions"]
        for field, expected in expected_fields.items():
            actual = set(expressions[field].get("references", []))
            if actual != expected:
                raise RuntimeError(
                    "Security Group identity reference drifted: "
                    f"{address}.{field} actual={sorted(actual)}"
                )
            assertion_count += 1

    expected_planned_addresses = {
        "module.network.aws_vpc_security_group_egress_rule.api_to_database",
        'module.network.aws_vpc_security_group_egress_rule.broker_clients["api"]',
        'module.network.aws_vpc_security_group_egress_rule.broker_clients["ml"]',
        'module.network.aws_vpc_security_group_egress_rule.task_dns_tcp["api"]',
        'module.network.aws_vpc_security_group_egress_rule.task_dns_tcp["ml"]',
        'module.network.aws_vpc_security_group_egress_rule.task_dns_tcp["web"]',
        'module.network.aws_vpc_security_group_egress_rule.task_dns_udp["api"]',
        'module.network.aws_vpc_security_group_egress_rule.task_dns_udp["ml"]',
        'module.network.aws_vpc_security_group_egress_rule.task_dns_udp["web"]',
        'module.network.aws_vpc_security_group_egress_rule.task_https["api"]',
        'module.network.aws_vpc_security_group_egress_rule.task_https["ml"]',
        'module.network.aws_vpc_security_group_egress_rule.task_https["web"]',
        "module.network.aws_vpc_security_group_egress_rule.vpc_link_to_web",
        "module.network.aws_vpc_security_group_egress_rule.web_to_api",
        "module.network.aws_vpc_security_group_ingress_rule.api_from_web",
        'module.network.aws_vpc_security_group_ingress_rule.broker_from_clients["api"]',
        'module.network.aws_vpc_security_group_ingress_rule.broker_from_clients["ml"]',
        "module.network.aws_vpc_security_group_ingress_rule.database_from_api",
        "module.network.aws_vpc_security_group_ingress_rule.web_from_vpc_link",
    }
    actual_planned_addresses = {
        resource["address"]
        for resource in resources
        if resource["type"]
        in {
            "aws_vpc_security_group_egress_rule",
            "aws_vpc_security_group_ingress_rule",
        }
    }
    if actual_planned_addresses != expected_planned_addresses:
        raise RuntimeError(
            "Expanded Security Group rule identities drifted: "
            f"actual={sorted(actual_planned_addresses)}"
        )
    return assertion_count + 1


def verify_security_contract(
    plan: dict[str, Any], resources: list[dict[str, Any]]
) -> int:
    contract = plan["planned_values"]["outputs"]["static_contract"]["value"]
    assertions = [
        contract["ownership"]["state_key"] == "environments/manual/terraform.tfstate",
        contract["ownership"]["tags"] == OWNERSHIP_TAGS,
        contract["network"]["nat_resources"] == 0,
        contract["network"]["internet_gateway_count"] == 1,
        contract["network"]["public_task_subnet_count"] == 2,
        contract["network"]["isolated_subnet_count"] == 2,
        contract["network"]["isolated_default_routes"] == 0,
        contract["network"]["public_inbound_cidrs"] == [],
        len(contract["network"]["security_group_edges"]) == 5,
        contract["ingress"]["public_boundary"]
        == "api-gateway-http-api-generated-https",
        contract["ingress"]["integration_connection"] == "VPC_LINK",
        contract["ingress"]["integration_target"] == "cloud-map:web",
        contract["ingress"]["alb_resources"] == 0,
        contract["ingress"]["custom_domain_resources"] == 0,
        contract["runtime"]["network_mode"] == "awsvpc",
        contract["runtime"]["launch_type"] == "FARGATE",
        contract["runtime"]["public_ip_assignment"] is True,
        contract["runtime"]["service_count"] == 3,
        contract["runtime"]["migration_is_service"] is False,
        contract["runtime"]["tasks"]["web"]["cpu"] == 256,
        contract["runtime"]["tasks"]["api"]["cpu"] == 512,
        contract["runtime"]["tasks"]["ml"]["cpu"] == 1024,
        contract["runtime"]["tasks"]["ml"]["database_secret"] is False,
        contract["runtime"]["tasks"]["ml"]["end_user_identity"] is False,
        contract["runtime"]["web_application_store_credentials"] is False,
        contract["state"]["postgresql"]["engine_version"] == "18",
        contract["state"]["postgresql"]["encrypted"] is True,
        contract["state"]["postgresql"]["publicly_accessible"] is False,
        contract["state"]["object_store"]["encrypted"] is True,
        contract["state"]["object_store"]["public_access_blocked"] is True,
        contract["state"]["object_store"]["force_destroy"] is True,
        contract["state"]["rabbitmq"]["engine_version"] == "4.2",
        contract["state"]["rabbitmq"]["instance_type"] == "mq.m7g.large",
        contract["state"]["rabbitmq"]["deployment_mode"] == "SINGLE_INSTANCE",
        contract["state"]["rabbitmq"]["publicly_accessible"] is False,
        contract["identity"]["public_client"] is True,
        contract["identity"]["client_secret_generated"] is False,
        contract["identity"]["authorization_code_flow"] is True,
        contract["identity"]["pkce_required"] is True,
        contract["identity"]["managed_login_version"] == 2,
        contract["identity"]["public_signup"] is False,
        contract["identity"]["seeded_users"] == 0,
        contract["identity"]["capability_claim"] == "cognito:groups",
    ]
    if not all(assertions):
        failed = [
            index for index, result in enumerate(assertions, start=1) if not result
        ]
        raise RuntimeError(f"Service-aware security assertions failed: {failed}")

    for resource in resources:
        if resource["type"] != "aws_vpc_security_group_ingress_rule":
            continue
        values = resource["values"]
        if values.get("cidr_ipv4") or values.get("cidr_ipv6"):
            raise RuntimeError(
                f"Direct CIDR ingress is forbidden: {resource['address']}"
            )

    ingress_inventory = Counter(
        (
            resource["values"]["ip_protocol"],
            resource["values"]["from_port"],
            resource["values"]["to_port"],
            resource["values"].get("cidr_ipv4"),
            resource["values"].get("cidr_ipv6"),
        )
        for resource in resources
        if resource["type"] == "aws_vpc_security_group_ingress_rule"
    )
    expected_ingress = Counter(
        {
            ("tcp", 3000, 3000, None, None): 1,
            ("tcp", 8000, 8000, None, None): 1,
            ("tcp", 5432, 5432, None, None): 1,
            ("tcp", 5671, 5671, None, None): 2,
        }
    )
    if ingress_inventory != expected_ingress:
        raise RuntimeError(f"Security Group ingress drifted: {ingress_inventory}")

    egress_inventory = Counter(
        (
            resource["values"]["ip_protocol"],
            resource["values"]["from_port"],
            resource["values"]["to_port"],
            resource["values"].get("cidr_ipv4"),
            resource["values"].get("cidr_ipv6"),
        )
        for resource in resources
        if resource["type"] == "aws_vpc_security_group_egress_rule"
    )
    expected_egress = Counter(
        {
            ("tcp", 3000, 3000, None, None): 1,
            ("tcp", 8000, 8000, None, None): 1,
            ("tcp", 5432, 5432, None, None): 1,
            ("tcp", 5671, 5671, None, None): 2,
            ("tcp", 443, 443, "0.0.0.0/0", None): 3,
            ("udp", 53, 53, "10.42.0.2/32", None): 3,
            ("tcp", 53, 53, "10.42.0.2/32", None): 3,
        }
    )
    if egress_inventory != expected_egress:
        raise RuntimeError(f"Security Group egress drifted: {egress_inventory}")

    image_references = plan["planned_values"]["outputs"]["bootstrap_references"][
        "value"
    ]["image_references"]
    if not all(
        "@sha256:" in reference and len(reference.rsplit("@sha256:", 1)[1]) == 64
        for reference in image_references.values()
    ):
        raise RuntimeError("Every planned image must be digest pinned")

    workload_roles = {
        task["workload_role"] for task in contract["runtime"]["tasks"].values()
    }
    if len(workload_roles) != 3:
        raise RuntimeError("Web, API, and ML must have three distinct workload roles")
    if contract["runtime"]["execution_role_arn"] in workload_roles:
        raise RuntimeError("Task execution and workload roles must remain distinct")
    reference_assertions = verify_security_group_reference_contract(plan, resources)
    return len(assertions) + 6 + reference_assertions


def verify_secret_and_output_contract(
    plan: dict[str, Any], resources: list[dict[str, Any]]
) -> int:
    outputs = plan["planned_values"]["outputs"]
    if not outputs["secret_references"]["sensitive"]:
        raise RuntimeError("Secret references output must be explicitly sensitive")
    public_outputs = set(outputs) - {"secret_references"}
    if any(outputs[name]["sensitive"] for name in public_outputs):
        raise RuntimeError("A deterministic public output was unexpectedly sensitive")

    required_sensitive = {
        "module.managed_state.aws_db_instance.postgresql": "password",
        "module.managed_state.aws_secretsmanager_secret_version.broker": (
            "secret_string"
        ),
        "module.managed_state.aws_secretsmanager_secret_version.database": (
            "secret_string"
        ),
        "module.managed_state.random_password.broker": "result",
        "module.managed_state.random_password.database": "result",
    }
    for address, field in required_sensitive.items():
        resource = resource_by_address(resources, address)
        if resource["values"].get(field) is not None:
            raise RuntimeError(f"Sensitive plan value became known: {address}.{field}")
        if resource["sensitive_values"].get(field) is not True:
            raise RuntimeError(f"Sensitive plan marking is missing: {address}.{field}")

    broker = resource_by_address(
        resources, "module.managed_state.aws_mq_broker.rabbitmq"
    )
    if broker["sensitive_values"].get("user") is not True:
        raise RuntimeError("Amazon MQ user credentials must remain plan-sensitive")
    if any("password" in user for user in broker["values"]["user"]):
        raise RuntimeError("Amazon MQ password appeared in planned resource values")

    serialized = json.dumps(plan, sort_keys=True)
    forbidden_literals = (
        "synthetic-plan-value-not-a-secret",
        "synthetic-generated-value",
    )
    if any(value in serialized for value in forbidden_literals):
        raise RuntimeError("A synthetic secret marker leaked into sanitized plan JSON")
    return len(required_sensitive) + len(public_outputs) + 5


def main() -> int:
    ARTIFACT_PATH.unlink(missing_ok=True)
    terraform = require_command("terraform")
    tflint = require_command("tflint")
    operator_action_contract = verify_operator_action_matrix()
    matrix = json.loads(OPERATOR_ACTION_MATRIX_PATH.read_text(encoding="utf-8"))
    console_iam_contract = verify_console_iam_contract(matrix)

    run(
        "Check environment Terraform formatting",
        [terraform, "fmt", "-check", "-recursive", str(ENVIRONMENT_ROOT)],
    )
    run(
        "Initialize environment providers without a remote backend",
        [
            terraform,
            f"-chdir={ENVIRONMENT_ROOT}",
            "init",
            "-backend=false",
            "-input=false",
            "-lockfile=readonly",
            "-no-color",
        ],
    )
    run(
        "Validate environment Terraform configuration",
        [terraform, f"-chdir={ENVIRONMENT_ROOT}", "validate", "-no-color"],
    )
    run(
        "Run AWS-free environment mock plans",
        [terraform, f"-chdir={ENVIRONMENT_ROOT}", "test", "-no-color"],
    )
    run(
        "Lint environment Terraform modules",
        [
            tflint,
            f"--chdir={ENVIRONMENT_ROOT}",
            "--config",
            ".tflint.hcl",
            "--format",
            "compact",
        ],
    )

    print("\n==> Build and scan sanitized fail-closed environment plan", flush=True)
    with tempfile.TemporaryDirectory(prefix="portfolio-aws-environment-") as directory:
        plan = create_sanitized_plan(terraform, Path(directory) / "environment.tfplan")

    resources, resource_count = verify_resource_inventory(plan)
    tagged_resource_count = verify_tags(resources)
    service_property_assertions = verify_planned_service_properties(resources)
    security_assertions = verify_security_contract(plan, resources)
    secret_assertions = verify_secret_and_output_contract(plan, resources)
    static_contract = plan["planned_values"]["outputs"]["static_contract"]["value"]
    contract_digest = hashlib.sha256(
        json.dumps(static_contract, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    lock_path = ENVIRONMENT_ROOT / ".terraform.lock.hcl"
    evidence = {
        "schemaVersion": 2,
        "sourceHead": source_head(),
        "terraformVersion": command_version(terraform, "version"),
        "tflintVersion": command_version(tflint, "--version"),
        "providerLockSha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
        "terraformMockPlanFiles": 1,
        "terraformMockRuns": 4,
        "plannedResourceCount": resource_count,
        "plannedResourceTypes": EXPECTED_RESOURCE_COUNTS,
        "operatorActionContract": operator_action_contract,
        "consoleIamContract": console_iam_contract,
        "taggedResourceCount": tagged_resource_count,
        "securityScanner": "repository-owned-plan-contract-v1",
        "servicePropertyAssertions": service_property_assertions,
        "securityAssertions": security_assertions,
        "secretAndOutputAssertions": secret_assertions,
        "staticContractSha256": contract_digest,
        "forbiddenResourceTypesPresent": [],
        "staticVerifierAwsApiCalls": 0,
        "staticVerifierAwsWrites": 0,
        "staticVerifierAwsResourcesCreated": 0,
        "liveAwsHistoryIncluded": False,
        "historicalConstructionAttempts": "3/3",
    }
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        "\nAWS environment static proof passed: "
        f"{resource_count} resources, {service_property_assertions} planned "
        f"service assertions, {security_assertions} security assertions, "
        "static-verifier AWS calls/writes/resources 0/0/0; live history excluded"
    )
    print(f"Evidence: {ARTIFACT_PATH.relative_to(REPOSITORY_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"AWS environment verification failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
