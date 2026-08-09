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
    "global-read",
    "request-tags",
    "resource-tags",
    "service-delegated",
}
CONSOLE_IAM_TOKENS = {
    "AWS_ACCOUNT_ID": "111122223333",
    "AWS_PARTITION": "aws",
    "AWS_REGION": "us-east-1",
    "ENVIRONMENT": "manual",
    "NAME_PREFIX": "example-portfolio",
    "OWNER_PRINCIPAL_ARN": "arn:aws:iam::111122223333:role/PortfolioBootstrapOwner",
    "REPOSITORY_IDENTITY": "example-owner/example-repository",
    "STATE_BUCKET_NAME": "example-portfolio-111122223333-us-east-1-state",
}


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


def condition_matches(statement: dict[str, Any], context: dict[str, str]) -> bool:
    conditions = statement.get("Condition", {})
    for operator, entries in conditions.items():
        if operator not in {"StringEquals", "StringLike"}:
            return False
        for key, expected in entries.items():
            actual = context.get(key)
            if actual is None:
                return False
            candidates = string_values(expected)
            if operator == "StringEquals" and actual not in candidates:
                return False
            if operator == "StringLike" and not any(
                fnmatch.fnmatchcase(actual, candidate) for candidate in candidates
            ):
                return False
    return True


def policy_allows(
    policy: dict[str, Any],
    action: str,
    resource: str,
    context: dict[str, str] | None = None,
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
    if symbol.startswith("iam-"):
        purpose = symbol.removeprefix("iam-").removesuffix("-role")
        return f"arn:{partition}:iam::{account}:role/{prefix}-{environment}-{purpose}"
    service = {
        "api-gateway": "apigateway",
        "cloudmap": "servicediscovery",
        "ec2": "ec2",
        "ecs": "ecs",
        "log": "logs",
        "mq": "mq",
        "rds": "rds",
        "secret": "secretsmanager",
        "cognito": "cognito-idp",
    }.get(symbol.split("-", 1)[0], symbol.split("-", 1)[0])
    return f"arn:{partition}:{service}:{region}:{account}:{symbol}/example"


def verify_console_iam_contract(matrix: dict[str, Any]) -> dict[str, Any]:
    manifest = rendered_console_json(CONSOLE_IAM_ROOT / "manifest.json")
    if manifest.get("schemaVersion") != 1:
        raise RuntimeError("Unknown Console IAM manifest schema")

    expected_policy_keys = {
        "operatorPermissions",
        "operatorBoundary",
        "taskExecution",
        "apiWorkload",
        "mlWorkload",
        "destroy",
    }
    policy_specs = manifest.get("managedPolicies", {})
    if set(policy_specs) != expected_policy_keys:
        raise RuntimeError("Console IAM managed-policy inventory drifted")
    if (
        policy_specs["operatorPermissions"]["name"]
        == policy_specs["operatorBoundary"]["name"]
    ):
        raise RuntimeError(
            "Operator permissions and boundary must be different objects"
        )
    if (
        policy_specs["operatorPermissions"]["document"]
        == policy_specs["operatorBoundary"]["document"]
    ):
        raise RuntimeError(
            "Operator permissions and boundary must use different documents"
        )

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
    if roles["operator_deployment"].get("permissions") != ["operatorPermissions"]:
        raise RuntimeError(
            "Operator must have exactly its separately named permissions policy"
        )
    if roles["web_workload"].get("permissions") != []:
        raise RuntimeError("Web workload must remain an empty-authority role")
    if roles["destroy"].get("permissions") != ["operatorPermissions", "destroy"]:
        raise RuntimeError(
            "Destroy must combine backend reads with separate delete authority"
        )

    trust_files = {role["trust"] for role in roles.values()}
    for trust_file in trust_files:
        trust = rendered_console_json(CONSOLE_IAM_ROOT / trust_file)
        if any(
            statement.get("Effect") == "Deny"
            for statement in trust.get("Statement", [])
        ):
            raise RuntimeError(
                f"Console IAM trust must not contain explicit Deny: {trust_file}"
            )

    permissions = policies["operatorPermissions"]
    boundary = policies["operatorBoundary"]
    destroy = policies["destroy"]
    rows = 0
    allowed_layer_decisions = 0
    for resource_type, action_rows in sorted(matrix["resourceActions"].items()):
        for row in action_rows:
            action, symbol = row[:2]
            resource = operator_resource(symbol)
            context = {
                key: str(value)
                for key, value in (row[3] if len(row) == 4 else {}).items()
            }
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

    state_bucket = "arn:aws:s3:::example-portfolio-111122223333-us-east-1-state"
    state_object = state_bucket + "/environments/manual/terraform.tfstate"
    lock_object = state_object + ".tflock"
    pass_context = {"iam:PassedToService": "ecs-tasks.amazonaws.com"}
    runtime_role = (
        "arn:aws:iam::111122223333:role/example-portfolio-manual-task-execution"
    )
    operator_role = (
        "arn:aws:iam::111122223333:role/example-portfolio-manual-operator-deployment"
    )
    negative_cases = {
        "identityCannotDeleteStateBucket": not policy_allows(
            permissions, "s3:DeleteBucket", state_bucket
        ),
        "boundaryCannotDeleteStateBucket": not policy_allows(
            boundary, "s3:DeleteBucket", state_bucket
        ),
        "identityCannotDeleteStateObject": not policy_allows(
            permissions, "s3:DeleteObject", state_object
        ),
        "boundaryCannotDeleteStateObject": not policy_allows(
            boundary, "s3:DeleteObject", state_object
        ),
        "identityCannotMutateIam": not policy_allows(
            permissions, "iam:AttachRolePolicy", runtime_role
        ),
        "boundaryCannotMutateIam": not policy_allows(
            boundary, "iam:AttachRolePolicy", runtime_role
        ),
        "identityCannotPassOperator": not policy_allows(
            permissions, "iam:PassRole", operator_role, pass_context
        ),
        "boundaryCannotPassOperator": not policy_allows(
            boundary, "iam:PassRole", operator_role, pass_context
        ),
    }
    positive_cases = {
        "identityCanDeleteLock": policy_allows(
            permissions, "s3:DeleteObject", lock_object
        ),
        "boundaryCanDeleteLock": policy_allows(
            boundary, "s3:DeleteObject", lock_object
        ),
        "identityCanPassRuntime": policy_allows(
            permissions, "iam:PassRole", runtime_role, pass_context
        ),
        "boundaryCanPassRuntime": policy_allows(
            boundary, "iam:PassRole", runtime_role, pass_context
        ),
        "boundaryHasIndependentSchedulerCeiling": (
            policy_allows(boundary, "scheduler:CreateSchedule", "*")
            and not policy_allows(permissions, "scheduler:CreateSchedule", "*")
        ),
        "destroyCanDeleteCloudMapHostedZone": policy_allows(
            destroy, "route53:DeleteHostedZone", "*"
        ),
        "boundaryCanDeleteCloudMapHostedZone": policy_allows(
            boundary, "route53:DeleteHostedZone", "*"
        ),
        "destroyCanCleanManagedNetworkInterfaces": (
            policy_allows(destroy, "ec2:DescribeNetworkInterfaces", "*")
            and policy_allows(destroy, "ec2:DetachNetworkInterface", "*")
            and not policy_allows(
                permissions, "ec2:DetachNetworkInterface", "*"
            )
        ),
        "boundaryCanCleanManagedNetworkInterfaces": (
            policy_allows(boundary, "ec2:DescribeNetworkInterfaces", "*")
            and policy_allows(boundary, "ec2:DetachNetworkInterface", "*")
        ),
    }
    failed = [
        name
        for name, passed in {**negative_cases, **positive_cases}.items()
        if not passed
    ]
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
        "invariantCases": len(negative_cases) + len(positive_cases),
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
            if ownership == "exact-resource" and resource == "*":
                raise RuntimeError(
                    f"Exact-resource action cannot use Resource '*': {row}"
                )
            if (
                ownership == "service-delegated"
                and action != "route53:CreateHostedZone"
            ):
                raise RuntimeError(f"Unexpected service-delegated action: {row}")
            if len(row) == 4 and not isinstance(row[3], dict):
                raise RuntimeError(f"Operator action context must be an object: {row}")
            rows.append(json.dumps([resource_type, *row], sort_keys=True))
    if len(rows) != len(set(rows)):
        raise RuntimeError(
            "Operator action matrix contains duplicate resource/action rows"
        )
    return {
        "provider": provider,
        "resourceTypes": len(resource_actions),
        "actionRows": len(rows),
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
    return len(assertions) + 6


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
        "schemaVersion": 1,
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
        "awsApiCalls": 0,
        "awsWrites": 0,
        "awsResourcesCreated": 0,
        "realEvaluationAttempts": "0/3",
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
        "AWS calls/writes/resources 0/0/0"
    )
    print(f"Evidence: {ARTIFACT_PATH.relative_to(REPOSITORY_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"AWS environment verification failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
