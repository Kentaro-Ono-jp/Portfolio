from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from aws_bootstrap_backend import backend_files, validate_backend_inputs


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_ROOT = REPOSITORY_ROOT / "infra" / "aws" / "bootstrap"
MATRIX_PATH = BOOTSTRAP_ROOT / "policy-matrix.json"
ARTIFACT_PATH = (
    REPOSITORY_ROOT / "artifacts" / "verification" / "aws-bootstrap-static.json"
)
TFVARS_PATH = "terraform.tfvars.example"
POLICY_EXPRESSION = """jsonencode({
  boundary = local.permissions_boundary_policy,
  global_identity = local.global_identity_policies,
  environment_identity = local.environment_identity_policies,
  human_trust = local.human_trust_policy,
  automation_trust = local.automation_trust_policy,
  environment_trust = local.environment_assume_role_policies,
  role_arns = merge(local.global_role_arns, local.environment_role_arns),
  ecr_arns = local.ecr_repository_arns,
  state_bucket_arn = local.state_bucket_arn,
  environment_state_arns = local.environment_state_arns,
  environment_lock_arns = local.environment_lock_arns,
  environment_app_bucket_arns = local.environment_app_bucket_arns,
  boundary_arn = local.boundary_policy_arn,
  github_provider_arn = var.github_oidc_provider_arn,
  owner_principal_arn = var.owner_principal_arn,
  bootstrap_state_key = var.bootstrap_state_key,
  policy_sizes = {
    boundary = length(local.permissions_boundary_policy),
    global_inline = { for name, policy in local.global_identity_policies : name => length(policy) },
    environment_inline = { for name, policy in local.environment_identity_policies : name => length(policy) },
    global_trust = {
      iam_manager = length(local.human_trust_policy),
      automation = length(local.automation_trust_policy)
    },
    environment_trust = { for name, policy in local.environment_assume_role_policies : name => length(policy) }
  },
  github_contract = {
    allowed_events = local.github_allowed_events,
    audience = "sts.amazonaws.com",
    environment = var.github_environment,
    ref = "refs/heads/main",
    repository = var.repository_identity,
    subject_template_keys = local.github_oidc_subject_template_keys,
    subjects = local.github_oidc_subjects,
    workflow = var.github_workflow_name,
    workflow_ref = var.github_workflow_ref
  }
})"""


def require_command(name: str) -> str:
    resolved = shutil.which(name)
    if resolved is None:
        raise RuntimeError(f"Required command is not available: {name}")
    return resolved


def run(label: str, command: list[str]) -> None:
    print(f"\n==> {label}", flush=True)
    subprocess.run(command, cwd=REPOSITORY_ROOT, check=True)


def terraform_payload(
    terraform: str, variable_overrides: dict[str, str] | None = None
) -> dict[str, Any]:
    expression = " ".join(
        line.strip() for line in POLICY_EXPRESSION.splitlines() if line.strip()
    )
    command = [
        terraform,
        f"-chdir={BOOTSTRAP_ROOT}",
        "console",
        "-no-color",
        f"-var-file={TFVARS_PATH}",
    ]
    command.extend(
        f"-var={name}={value}"
        for name, value in sorted((variable_overrides or {}).items())
    )
    completed = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        input=f"{expression}\n",
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "terraform console failed: "
            f"stdout={completed.stdout.strip()} stderr={completed.stderr.strip()}"
        )
    encoded = json.loads(completed.stdout.strip())
    payload = json.loads(encoded)
    for key in (
        "boundary",
        "human_trust",
        "automation_trust",
    ):
        payload[key] = json.loads(payload[key])
    for key in ("global_identity", "environment_identity", "environment_trust"):
        payload[key] = {
            name: json.loads(document) for name, document in payload[key].items()
        }
    return payload


def values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def substitute(value: str, context: dict[str, Any]) -> str:
    rendered = value
    for key, replacement in context.items():
        if isinstance(replacement, str):
            rendered = rendered.replace(f"${{{key}}}", replacement)
    return rendered


def action_matches(requested: str, configured: Any) -> bool:
    requested_lower = requested.lower()
    return any(
        fnmatch.fnmatchcase(requested_lower, pattern.lower())
        for pattern in values(configured)
    )


def resource_matches(requested: str, configured: Any, context: dict[str, Any]) -> bool:
    return any(
        fnmatch.fnmatchcase(requested, substitute(pattern, context))
        for pattern in values(configured)
    )


def condition_matches(condition: dict[str, Any], context: dict[str, Any]) -> bool:
    for operator, clauses in condition.items():
        for key, expected_value in clauses.items():
            expected = [substitute(item, context) for item in values(expected_value)]
            actual = context.get(key)
            actual_values = [] if actual is None else values(actual)
            if operator in {"StringEquals", "ArnEquals", "Bool"}:
                if not actual_values or not any(
                    item in expected for item in actual_values
                ):
                    return False
            elif operator in {"StringLike", "ArnLike"}:
                if actual is None or not any(
                    fnmatch.fnmatchcase(actual, pattern) for pattern in expected
                ):
                    return False
            elif operator in {"StringNotEquals", "ArnNotEquals"}:
                if any(item in expected for item in actual_values):
                    return False
            elif operator == "ForAllValues:StringEquals":
                if any(item not in expected for item in actual_values):
                    return False
            else:
                raise RuntimeError(f"Unsupported policy condition operator: {operator}")
    return True


def matching_effects(
    policy: dict[str, Any],
    *,
    action: str,
    resource: str,
    context: dict[str, Any],
) -> set[str]:
    effects: set[str] = set()
    for statement in policy.get("Statement", []):
        if "NotAction" in statement or "NotResource" in statement:
            raise RuntimeError(
                "NotAction and NotResource are forbidden in bootstrap policy"
            )
        if not action_matches(action, statement.get("Action", [])):
            continue
        if not resource_matches(resource, statement.get("Resource", "*"), context):
            continue
        if not condition_matches(statement.get("Condition", {}), context):
            continue
        effects.add(statement["Effect"])
    return effects


def identity_decision(
    identity: dict[str, Any],
    boundary: dict[str, Any],
    *,
    action: str,
    resource: str,
    context: dict[str, Any],
) -> str:
    # AWS STS documents GetCallerIdentity as permissionless, including when an
    # applicable identity policy explicitly denies it.
    if action.lower() == "sts:getcalleridentity":
        return "allowed"
    identity_effects = matching_effects(
        identity, action=action, resource=resource, context=context
    )
    boundary_effects = matching_effects(
        boundary, action=action, resource=resource, context=context
    )
    if "Deny" in identity_effects or "Deny" in boundary_effects:
        return "denied"
    if "Allow" in identity_effects and "Allow" in boundary_effects:
        return "allowed"
    return "denied"


def principal_matches(statement: dict[str, Any], kind: str, principal: str) -> bool:
    configured = statement.get("Principal")
    if configured == "*":
        return True
    if not isinstance(configured, dict) or kind not in configured:
        return False
    return any(
        fnmatch.fnmatchcase(principal, item) for item in values(configured[kind])
    )


def trust_decision(
    policy: dict[str, Any],
    *,
    action: str,
    principal_type: str,
    principal: str,
    context: dict[str, str],
) -> str:
    effects: set[str] = set()
    for statement in policy.get("Statement", []):
        if not action_matches(action, statement.get("Action", [])):
            continue
        if not principal_matches(statement, principal_type, principal):
            continue
        if not condition_matches(statement.get("Condition", {}), context):
            continue
        effects.add(statement["Effect"])
    if "Deny" in effects:
        return "denied"
    return "allowed" if "Allow" in effects else "denied"


def resolve_symbol(value: str, payload: dict[str, Any]) -> str:
    if value == "*":
        return value
    if value.startswith("arn:") or value.endswith(".amazonaws.com"):
        return value
    if value == "boundary":
        return payload["boundary_arn"]
    if value == "state-bucket":
        return payload["state_bucket_arn"]
    if value == "bootstrap-state":
        return f"{payload['state_bucket_arn']}/{payload['bootstrap_state_key']}"
    if value == "owner-principal":
        return payload["owner_principal_arn"]
    if value == "github-provider":
        return payload["github_provider_arn"]
    if value == "arbitrary-role":
        return "arn:aws:iam::999988887777:role/UnrelatedAdministrator"
    if value == "arbitrary-user":
        return "arn:aws:iam::111122223333:user/UnboundedUser"
    if value == "admin-policy":
        return "arn:aws:iam::aws:policy/AdministratorAccess"
    if value.startswith("role:"):
        return payload["role_arns"][value.removeprefix("role:")]
    if value.startswith("state-lock:"):
        return payload["environment_lock_arns"][value.removeprefix("state-lock:")]
    if value.startswith("state:"):
        return payload["environment_state_arns"][value.removeprefix("state:")]
    if value.startswith("ecr:"):
        return payload["ecr_arns"][value.removeprefix("ecr:")]
    if value.startswith("app-object:"):
        environment, object_key = value.removeprefix("app-object:").split("/", 1)
        return f"{payload['environment_app_bucket_arns'][environment]}/{object_key}"
    if value.startswith("app:"):
        return payload["environment_app_bucket_arns"][value.removeprefix("app:")]
    if value.startswith("codebuild:"):
        environment = value.removeprefix("codebuild:")
        return (
            "arn:aws:codebuild:us-east-1:111122223333:project/"
            f"example-portfolio-{environment}-destroy"
        )
    if value.startswith("secret:"):
        environment, name = value.removeprefix("secret:").split("/", 1)
        return (
            "arn:aws:secretsmanager:us-east-1:111122223333:secret:"
            f"example-portfolio-{environment}-{name}"
        )
    if value.startswith("rds:"):
        environment = value.removeprefix("rds:")
        return (
            f"arn:aws:rds:us-east-1:111122223333:db:example-portfolio-{environment}-db"
        )
    if value.startswith("cognito:"):
        return "arn:aws:cognito-idp:us-east-1:111122223333:userpool/example"
    raise RuntimeError(f"Unknown policy-matrix symbol: {value}")


def role_environment(role: str) -> str:
    return role.split("/", 1)[0] if "/" in role else "shared"


def role_purpose(role: str) -> str:
    return role.split("/", 1)[1] if "/" in role else role.replace("_", "-")


def identity_policy(role: str, payload: dict[str, Any]) -> dict[str, Any]:
    source = "environment_identity" if "/" in role else "global_identity"
    return payload[source][role]


def trust_policy(role: str, payload: dict[str, Any]) -> dict[str, Any]:
    if role == "automation":
        return payload["automation_trust"]
    if role == "iam_manager":
        return payload["human_trust"]
    return payload["environment_trust"][role]


def resolved_context(
    raw: dict[str, Any], role: str, payload: dict[str, Any]
) -> dict[str, Any]:
    context = {
        key: resolve_symbol(value, payload)
        if isinstance(value, str) and value in {"boundary", "admin-policy"}
        else value
        for key, value in raw.items()
    }
    context.setdefault("aws:PrincipalTag/PortfolioEnvironment", role_environment(role))
    context.setdefault("aws:PrincipalTag/PortfolioPurpose", role_purpose(role))
    return context


def validate_policy_matrix_document(matrix: Any) -> dict[str, Any]:
    if not isinstance(matrix, dict):
        raise RuntimeError("Policy matrix must be a JSON object")
    schema_version = matrix.get("schemaVersion")
    if type(schema_version) is not int or schema_version != 1:
        raise RuntimeError("Unknown policy matrix schema")
    return matrix


def load_policy_matrix() -> dict[str, Any]:
    return validate_policy_matrix_document(
        json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    )


def verify_policy_matrix_schema_contract() -> dict[str, Any]:
    matrix = load_policy_matrix()
    for boolean_version in (True, False):
        mutation = json.loads(
            json.dumps({**matrix, "schemaVersion": boolean_version}, sort_keys=True)
        )
        try:
            validate_policy_matrix_document(mutation)
        except RuntimeError as error:
            if str(error) != "Unknown policy matrix schema":
                raise
        else:
            raise RuntimeError(
                "Policy matrix accepted a JSON boolean schema discriminator"
            )
    return matrix


def verify_matrix(payload: dict[str, Any]) -> dict[str, int]:
    matrix = verify_policy_matrix_schema_contract()
    counts = {
        "identityAllowed": 0,
        "identityDenied": 0,
        "trustAllowed": 0,
        "trustDenied": 0,
    }

    for case in matrix["identityCases"]:
        role = case["role"]
        context = resolved_context(case.get("context", {}), role, payload)
        actual = identity_decision(
            identity_policy(role, payload),
            payload["boundary"],
            action=case["action"],
            resource=resolve_symbol(case["resource"], payload),
            context=context,
        )
        if actual != case["expected"]:
            raise RuntimeError(
                f"Identity case failed: {case['name']}: expected {case['expected']}, got {actual}"
            )
        counts[f"identity{actual.title()}"] += 1

    for case in matrix["trustCases"]:
        role = case["role"]
        actual = trust_decision(
            trust_policy(role, payload),
            action=case["action"],
            principal_type=case["principalType"],
            principal=resolve_symbol(case["principal"], payload),
            context=resolved_context(case.get("context", {}), role, payload),
        )
        if actual != case["expected"]:
            raise RuntimeError(
                f"Trust case failed: {case['name']}: expected {case['expected']}, got {actual}"
            )
        counts[f"trust{actual.title()}"] += 1

    return counts


def verify_policy_structure(payload: dict[str, Any]) -> None:
    identity_policies = list(payload["global_identity"].values()) + list(
        payload["environment_identity"].values()
    )
    for policy in identity_policies:
        for statement in policy["Statement"]:
            actions = values(statement["Action"])
            if any(action == "*" or action.lower() == "iam:*" for action in actions):
                raise RuntimeError("Identity policies may not grant wildcard authority")
            if any(action.lower() == "iam:passrole" for action in actions):
                if statement.get("Resource") == "*":
                    raise RuntimeError("iam:PassRole must name exact role resources")
                condition = statement.get("Condition", {}).get("StringEquals", {})
                if "iam:PassedToService" not in condition:
                    raise RuntimeError("iam:PassRole must bind iam:PassedToService")

    for statement in payload["boundary"]["Statement"]:
        if not action_matches("iam:PassRole", statement.get("Action", [])):
            continue
        if any(
            wildcard in resource
            for resource in values(statement.get("Resource", []))
            for wildcard in ("*", "?")
        ):
            raise RuntimeError(
                "Permissions Boundary iam:PassRole must name exact role resources"
            )

    if sorted(payload["github_contract"]["allowed_events"]) != [
        "schedule",
        "workflow_dispatch",
    ]:
        raise RuntimeError("Future GitHub authority must stay event-class restricted")
    expected_template_keys = ["repo", "context", "job_workflow_ref", "event_name"]
    if payload["github_contract"]["subject_template_keys"] != expected_template_keys:
        raise RuntimeError("GitHub OIDC subject template must bind event_name")
    expected_subjects = {
        (
            "repo:example-owner/example-repository:environment:aws-deployment:"
            "job_workflow_ref:example-owner/example-repository/.github/workflows/"
            f"aws-deploy.yml@refs/heads/main:event_name:{event_name}"
        )
        for event_name in ("schedule", "workflow_dispatch")
    }
    if set(payload["github_contract"]["subjects"]) != expected_subjects:
        raise RuntimeError("GitHub OIDC subjects must encode only the allowed events")
    trust_subjects = payload["automation_trust"]["Statement"][0]["Condition"][
        "StringEquals"
    ]["token.actions.githubusercontent.com:sub"]
    if set(values(trust_subjects)) != expected_subjects:
        raise RuntimeError("Allowed GitHub events must be connected to trust sub")
    if set(payload["ecr_arns"]) != {"api", "ml", "web"}:
        raise RuntimeError(
            "ECR contract must contain independent Web, API, and ML repositories"
        )
    if len(payload["environment_identity"]) != 16:
        raise RuntimeError("Synthetic contract must expose eight roles per environment")

    sizes = payload["policy_sizes"]
    if sizes["boundary"] > 6144:
        raise RuntimeError(
            f"Permissions Boundary exceeds 6144 characters: {sizes['boundary']}"
        )
    if sizes["boundary"] > 5632:
        raise RuntimeError(
            "Permissions Boundary consumes its 512-character headroom reserve: "
            f"{sizes['boundary']}/6144"
        )
    oversized_inline = {
        name: size
        for name, size in {
            **sizes["global_inline"],
            **sizes["environment_inline"],
        }.items()
        if size > 10240
    }
    if oversized_inline:
        raise RuntimeError(f"Role inline-policy quota exceeded: {oversized_inline}")
    inline_without_reserve = {
        name: size
        for name, size in {
            **sizes["global_inline"],
            **sizes["environment_inline"],
        }.items()
        if size > 9728
    }
    if inline_without_reserve:
        raise RuntimeError(
            f"Role inline-policy headroom reserve consumed: {inline_without_reserve}"
        )
    oversized_trust = {
        name: size
        for name, size in {
            **sizes["global_trust"],
            **sizes["environment_trust"],
        }.items()
        if size > 2048
    }
    if oversized_trust:
        raise RuntimeError(f"Role trust-policy quota exceeded: {oversized_trust}")

    manager_actions = {
        action.lower()
        for statement in payload["global_identity"]["iam_manager"]["Statement"]
        for action in values(statement["Action"])
    }
    forbidden_manager_actions = {
        "iam:attachrolepolicy",
        "iam:deleterolepolicy",
        "iam:detachrolepolicy",
        "iam:putrolepolicy",
    }
    if manager_actions & forbidden_manager_actions:
        raise RuntimeError("IAM manager must not mutate environment-role policies")
    if "iam:deleterole" in manager_actions:
        raise RuntimeError("IAM manager must not delete Terraform-owned roles")


def verify_policy_structure_mutations(payload: dict[str, Any]) -> int:
    mutations: list[tuple[str, dict[str, Any], str]] = []

    boundary_oversize = json.loads(json.dumps(payload))
    boundary_oversize["policy_sizes"]["boundary"] = 6145
    mutations.append(
        ("managed-policy quota", boundary_oversize, "Permissions Boundary exceeds")
    )

    boundary_headroom = json.loads(json.dumps(payload))
    boundary_headroom["policy_sizes"]["boundary"] = 5633
    mutations.append(
        (
            "managed-policy headroom",
            boundary_headroom,
            "Permissions Boundary consumes its 512-character headroom reserve",
        )
    )

    inline_oversize = json.loads(json.dumps(payload))
    inline_oversize["policy_sizes"]["global_inline"]["iam_manager"] = 10241
    mutations.append(
        ("inline-policy quota", inline_oversize, "Role inline-policy quota exceeded")
    )

    inline_headroom = json.loads(json.dumps(payload))
    inline_headroom["policy_sizes"]["global_inline"]["iam_manager"] = 9729
    mutations.append(
        (
            "inline-policy headroom",
            inline_headroom,
            "Role inline-policy headroom reserve consumed",
        )
    )

    trust_oversize = json.loads(json.dumps(payload))
    trust_oversize["policy_sizes"]["global_trust"]["automation"] = 2049
    mutations.append(
        ("trust-policy quota", trust_oversize, "Role trust-policy quota exceeded")
    )

    manager_mutation = json.loads(json.dumps(payload))
    manager_mutation["global_identity"]["iam_manager"]["Statement"].append(
        {
            "Effect": "Allow",
            "Action": "iam:PutRolePolicy",
            "Resource": "*",
        }
    )
    mutations.append(
        (
            "delegated policy mutation",
            manager_mutation,
            "IAM manager must not mutate environment-role policies",
        )
    )

    disconnected_event = json.loads(json.dumps(payload))
    disconnected_event["github_contract"]["allowed_events"].append("push")
    mutations.append(
        (
            "disconnected event metadata",
            disconnected_event,
            "Future GitHub authority must stay event-class restricted",
        )
    )

    wildcard_pass_role = json.loads(json.dumps(payload))
    for statement in wildcard_pass_role["boundary"]["Statement"]:
        if action_matches("iam:PassRole", statement.get("Action", [])):
            statement["Resource"] = "*"
            break
    mutations.append(
        (
            "wildcard boundary PassRole",
            wildcard_pass_role,
            "Permissions Boundary iam:PassRole must name exact role resources",
        )
    )

    manager_delete = json.loads(json.dumps(payload))
    manager_delete["global_identity"]["iam_manager"]["Statement"].append(
        {
            "Effect": "Allow",
            "Action": "iam:DeleteRole",
            "Resource": "*",
        }
    )
    mutations.append(
        (
            "delegated role deletion",
            manager_delete,
            "IAM manager must not delete Terraform-owned roles",
        )
    )

    for name, mutation, expected_error in mutations:
        try:
            verify_policy_structure(mutation)
        except RuntimeError as error:
            if expected_error not in str(error):
                raise RuntimeError(
                    f"Policy structure mutation {name} failed for the wrong reason: "
                    f"{error}"
                ) from error
        else:
            raise RuntimeError(f"Policy structure mutation was accepted: {name}")
    return len(mutations)


def verify_delegated_pass_role_ceiling(payload: dict[str, Any]) -> int:
    adversarial_identity = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "iam:PassRole",
                "Resource": "*",
            }
        ],
    }
    passed_to_services = (
        "ecs-tasks.amazonaws.com",
        "scheduler.amazonaws.com",
        "codebuild.amazonaws.com",
        "lambda.amazonaws.com",
    )
    expected_service = {
        "task-execution": "ecs-tasks.amazonaws.com",
        "web-workload": "ecs-tasks.amazonaws.com",
        "api-workload": "ecs-tasks.amazonaws.com",
        "ml-workload": "ecs-tasks.amazonaws.com",
        "scheduler": "scheduler.amazonaws.com",
        "codebuild-destroy": "codebuild.amazonaws.com",
    }
    target_roles = {
        **payload["role_arns"],
        "manual/evil-workload": (
            "arn:aws:iam::111122223333:role/example-portfolio/"
            "example-portfolio-manual-evil-workload"
        ),
        "monthly/evil-workload": (
            "arn:aws:iam::111122223333:role/example-portfolio/"
            "example-portfolio-monthly-evil-workload"
        ),
        "manual/web-workload-copy": (
            "arn:aws:iam::111122223333:role/example-portfolio/"
            "example-portfolio-manual-web-workload-copy"
        ),
        "monthly/task-execution-copy": (
            "arn:aws:iam::111122223333:role/example-portfolio/"
            "example-portfolio-monthly-task-execution-copy"
        ),
        "external/administrator": (
            "arn:aws:iam::999988887777:role/UnrelatedAdministrator"
        ),
    }
    declared_environment_targets = set(payload["environment_identity"])
    checked = 0
    for source_role in sorted(payload["role_arns"]):
        source_environment = role_environment(source_role)
        source_purpose = role_purpose(source_role)
        for target_role, target_arn in sorted(target_roles.items()):
            target_environment = role_environment(target_role)
            target_purpose = role_purpose(target_role)
            for passed_to_service in passed_to_services:
                context = resolved_context(
                    {"iam:PassedToService": passed_to_service},
                    source_role,
                    payload,
                )
                actual = identity_decision(
                    adversarial_identity,
                    payload["boundary"],
                    action="iam:PassRole",
                    resource=target_arn,
                    context=context,
                )
                expected = (
                    "allowed"
                    if source_purpose == "operator-deployment"
                    and target_role in declared_environment_targets
                    and source_environment == target_environment
                    and expected_service.get(target_purpose) == passed_to_service
                    else "denied"
                )
                if actual != expected:
                    raise RuntimeError(
                        "Delegated PassRole ceiling failed: "
                        f"{source_role} -> {target_role} via {passed_to_service}: "
                        f"expected {expected}, got {actual}"
                    )
                checked += 1
    return checked


def verify_operator_control_plane(payload: dict[str, Any]) -> int:
    allow_all = {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}],
    }
    request_tags = {
        "aws:RequestTag/PortfolioEnvironment": "manual",
        "aws:RequestTag/PortfolioManaged": "true",
        "aws:RequestTag/PortfolioPersistent": "false",
        "aws:RequestTag/PortfolioRepository": payload["github_contract"]["repository"],
        "aws:TagKeys": [
            "PortfolioEnvironment",
            "PortfolioManaged",
            "PortfolioPersistent",
            "PortfolioRepository",
        ],
    }
    resource_tags = {
        "aws:ResourceTag/PortfolioEnvironment": "manual",
        "aws:ResourceTag/PortfolioManaged": "true",
        "aws:ResourceTag/PortfolioPersistent": "false",
        "aws:ResourceTag/PortfolioRepository": payload["github_contract"]["repository"],
    }
    all_allowed = {
        "effective": "allowed",
        "identity": "allowed",
        "boundary": "allowed",
    }
    ownership_denied = {
        "effective": "denied",
        "identity": "denied",
        "boundary": "allowed",
    }
    http_api_write_resources = (
        ("apigateway:PATCH", "/apis/api-example"),
        ("apigateway:PATCH", "/apis/api-example/authorizers/auth-example"),
        ("apigateway:PATCH", "/apis/api-example/deployments/dep-example"),
        ("apigateway:PATCH", "/apis/api-example/integrations/int-example"),
        (
            "apigateway:PATCH",
            "/apis/api-example/integrations/int-example/"
            "integrationresponses/resp-example",
        ),
        ("apigateway:PATCH", "/apis/api-example/models/model-example"),
        ("apigateway:PATCH", "/apis/api-example/routes/route-example"),
        (
            "apigateway:PATCH",
            "/apis/api-example/routes/route-example/requestparameters/param-example",
        ),
        (
            "apigateway:PATCH",
            "/apis/api-example/routes/route-example/routeresponses/resp-example",
        ),
        ("apigateway:PATCH", "/apis/api-example/stages/stage-example"),
        ("apigateway:POST", "/apis/api-example/authorizers"),
        ("apigateway:POST", "/apis/api-example/deployments"),
        (
            "apigateway:POST",
            "/apis/api-example/integrations/int-example/"
            "integrationresponses/resp-example",
        ),
        (
            "apigateway:POST",
            "/apis/api-example/integrations/int-example/integrationresponses",
        ),
        ("apigateway:POST", "/apis/api-example/integrations"),
        ("apigateway:POST", "/apis/api-example/models"),
        (
            "apigateway:POST",
            "/apis/api-example/routes/route-example/routeresponses",
        ),
        ("apigateway:POST", "/apis/api-example/routes"),
        ("apigateway:POST", "/apis/api-example/stages"),
        ("apigateway:PUT", "/apis/api-example"),
        (
            "apigateway:PUT",
            "/apis/api-example/integrations/int-example/"
            "integrationresponses/resp-example",
        ),
    )
    rendered_http_write_actions = {
        action
        for statement in payload["environment_identity"]["manual/operator-deployment"][
            "Statement"
        ]
        if any(
            fnmatch.fnmatchcase(
                "arn:aws:apigateway:us-east-1::/apis/api-example",
                resource,
            )
            for resource in values(statement.get("Resource", []))
        )
        for action in values(statement.get("Action", []))
        if action.startswith("apigateway:") and action != "apigateway:GET"
    }
    enumerated_http_write_actions = {action for action, _ in http_api_write_resources}
    if rendered_http_write_actions != enumerated_http_write_actions:
        raise RuntimeError(
            "HTTP API write-form inventory does not match rendered actions: "
            f"rendered={sorted(rendered_http_write_actions)} "
            f"enumerated={sorted(enumerated_http_write_actions)}"
        )
    http_api_write_cases = tuple(
        (
            f"HTTP API write form {action} {resource_path}",
            action,
            f"arn:aws:apigateway:us-east-1::{resource_path}",
            resource_tags,
            "resource",
            all_allowed,
        )
        for action, resource_path in http_api_write_resources
    )
    cases = (
        ("EC2 inventory", "ec2:DescribeVpcs", "*", {}, None, all_allowed),
        (
            "EC2 creation",
            "ec2:CreateVpc",
            "*",
            request_tags,
            "request",
            all_allowed,
        ),
        (
            "EC2 dependent creation tagging",
            "ec2:CreateTags",
            "arn:aws:ec2:us-east-1:111122223333:vpc/vpc-new",
            {**request_tags, "ec2:CreateAction": "CreateVpc"},
            "request",
            all_allowed,
        ),
        (
            "EC2 direct retagging",
            "ec2:CreateTags",
            "arn:aws:ec2:us-east-1:111122223333:vpc/vpc-unowned",
            request_tags,
            None,
            ownership_denied,
        ),
        (
            "EC2 mutation",
            "ec2:AuthorizeSecurityGroupIngress",
            "arn:aws:ec2:us-east-1:111122223333:security-group/sg-example",
            resource_tags,
            "resource",
            all_allowed,
        ),
        (
            "EC2 tagged security-group rule creation",
            "ec2:AuthorizeSecurityGroupIngress",
            ("arn:aws:ec2:us-east-1:111122223333:security-group-rule/sgr-example"),
            request_tags,
            "request",
            all_allowed,
        ),
        (
            "EC2 tagged security-group rule dependent tagging",
            "ec2:CreateTags",
            ("arn:aws:ec2:us-east-1:111122223333:security-group-rule/sgr-example"),
            {
                **request_tags,
                "ec2:CreateAction": "AuthorizeSecurityGroupIngress",
            },
            "request",
            all_allowed,
        ),
        (
            "HTTP API creation",
            "apigateway:POST",
            "arn:aws:apigateway:us-east-1::/apis",
            request_tags,
            "request",
            all_allowed,
        ),
        *http_api_write_cases,
        (
            "Cognito user-pool creation",
            "cognito-idp:CreateUserPool",
            "*",
            request_tags,
            "request",
            all_allowed,
        ),
        (
            "Cognito tagging",
            "cognito-idp:TagResource",
            "arn:aws:cognito-idp:us-east-1:111122223333:userpool/us-east-1_example",
            {**request_tags, **resource_tags},
            "both",
            all_allowed,
        ),
        (
            "Cognito unowned-resource tagging",
            "cognito-idp:TagResource",
            "arn:aws:cognito-idp:us-east-1:111122223333:userpool/us-east-1_unowned",
            request_tags,
            None,
            ownership_denied,
        ),
        (
            "Cloud Map namespace creation",
            "servicediscovery:CreateHttpNamespace",
            "*",
            request_tags,
            "request",
            all_allowed,
        ),
        (
            "Cloud Map service creation against owned namespace",
            "servicediscovery:CreateService",
            "arn:aws:servicediscovery:us-east-1:111122223333:namespace/ns-example",
            resource_tags,
            "resource",
            all_allowed,
        ),
        (
            "Cloud Map service creation for new service",
            "servicediscovery:CreateService",
            "arn:aws:servicediscovery:us-east-1:111122223333:service/srv-new",
            request_tags,
            "request",
            all_allowed,
        ),
        (
            "Cloud Map tagging",
            "servicediscovery:TagResource",
            "arn:aws:servicediscovery:us-east-1:111122223333:namespace/ns-example",
            request_tags,
            "request",
            all_allowed,
        ),
    )
    operator_identity = payload["environment_identity"]["manual/operator-deployment"]
    checked = 0
    for name, action, resource, raw_context, ownership_context, base_expected in cases:
        variants = [("base", raw_context, base_expected)]
        if ownership_context is not None and base_expected == all_allowed:
            ownership_prefix = (
                "aws:ResourceTag/"
                if ownership_context in {"resource", "both"}
                else "aws:RequestTag/"
            )
            cross_environment = dict(raw_context)
            cross_environment[f"{ownership_prefix}PortfolioEnvironment"] = "monthly"
            variants.append(("cross-environment", cross_environment, ownership_denied))
            cross_repository = dict(raw_context)
            cross_repository[f"{ownership_prefix}PortfolioRepository"] = (
                "other-owner/other-repository"
            )
            variants.append(("cross-repository", cross_repository, ownership_denied))
            if ownership_context in {"request", "both"}:
                extra_tag_key = dict(raw_context)
                extra_tag_key["aws:TagKeys"] = [
                    *values(raw_context["aws:TagKeys"]),
                    "PortfolioOwner",
                ]
                variants.append(("extra-tag-key", extra_tag_key, ownership_denied))
        for variant, variant_context, expected_by_layer in variants:
            context = resolved_context(
                variant_context, "manual/operator-deployment", payload
            )
            decisions = {
                "effective": identity_decision(
                    operator_identity,
                    payload["boundary"],
                    action=action,
                    resource=resource,
                    context=context,
                ),
                "identity": identity_decision(
                    operator_identity,
                    allow_all,
                    action=action,
                    resource=resource,
                    context=context,
                ),
                "boundary": identity_decision(
                    allow_all,
                    payload["boundary"],
                    action=action,
                    resource=resource,
                    context=context,
                ),
            }
            failures = {
                layer: decision
                for layer, decision in decisions.items()
                if decision != expected_by_layer[layer]
            }
            if failures:
                raise RuntimeError(
                    "Operator control-plane ceiling failed: "
                    f"{name} {variant} expected {expected_by_layer}, got {failures}"
                )
            checked += len(decisions)
    return checked


def verify_delegated_policy_mutation_ceiling(payload: dict[str, Any]) -> int:
    mutation_actions = (
        "iam:AttachRolePolicy",
        "iam:DeleteRolePolicy",
        "iam:DetachRolePolicy",
        "iam:PutRolePolicy",
    )
    checked = 0
    for target_role, target_arn in sorted(payload["role_arns"].items()):
        if "/" not in target_role:
            continue
        target_environment = role_environment(target_role)
        target_purpose = role_purpose(target_role)
        context = resolved_context(
            {
                "aws:ResourceTag/PortfolioEnvironment": target_environment,
                "aws:ResourceTag/PortfolioManaged": "true",
                "aws:ResourceTag/PortfolioPersistent": "true",
                "aws:ResourceTag/PortfolioPurpose": target_purpose,
                "aws:ResourceTag/PortfolioRepository": (
                    "example-owner/example-repository"
                ),
            },
            "iam_manager",
            payload,
        )
        for action in mutation_actions:
            actual = identity_decision(
                payload["global_identity"]["iam_manager"],
                payload["boundary"],
                action=action,
                resource=target_arn,
                context=context,
            )
            if actual != "denied":
                raise RuntimeError(
                    "Delegated role-policy mutation ceiling failed: "
                    f"{action} on {target_role} was {actual}"
                )
            checked += 1
    return checked


def verify_tagged_destroy_ceiling(payload: dict[str, Any]) -> int:
    allow_all = {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}],
    }
    resources = (
        ("apigateway:DELETE", "arn:aws:apigateway:us-east-1::/apis/example"),
        (
            "cognito-idp:DeleteUserPool",
            "arn:aws:cognito-idp:us-east-1:111122223333:userpool/us-east-1_example",
        ),
        (
            "servicediscovery:DeleteNamespace",
            "arn:aws:servicediscovery:us-east-1:111122223333:namespace/ns-example",
        ),
        (
            "servicediscovery:DeleteService",
            "arn:aws:servicediscovery:us-east-1:111122223333:service/srv-example",
        ),
    )
    tag_variants = (
        (
            "owned",
            {
                "aws:ResourceTag/PortfolioEnvironment": "manual",
                "aws:ResourceTag/PortfolioManaged": "true",
                "aws:ResourceTag/PortfolioPersistent": "false",
                "aws:ResourceTag/PortfolioRepository": (
                    payload["github_contract"]["repository"]
                ),
            },
            {
                "effective": "allowed",
                "identity": "allowed",
                "boundary": "allowed",
            },
        ),
        (
            "cross-environment",
            {
                "aws:ResourceTag/PortfolioEnvironment": "monthly",
                "aws:ResourceTag/PortfolioManaged": "true",
                "aws:ResourceTag/PortfolioPersistent": "false",
                "aws:ResourceTag/PortfolioRepository": (
                    payload["github_contract"]["repository"]
                ),
            },
            {
                "effective": "denied",
                "identity": "denied",
                "boundary": "allowed",
            },
        ),
        (
            "cross-repository",
            {
                "aws:ResourceTag/PortfolioEnvironment": "manual",
                "aws:ResourceTag/PortfolioManaged": "true",
                "aws:ResourceTag/PortfolioPersistent": "false",
                "aws:ResourceTag/PortfolioRepository": ("other-owner/other-repository"),
            },
            {
                "effective": "denied",
                "identity": "denied",
                "boundary": "allowed",
            },
        ),
        (
            "unmanaged",
            {
                "aws:ResourceTag/PortfolioEnvironment": "manual",
                "aws:ResourceTag/PortfolioManaged": "false",
                "aws:ResourceTag/PortfolioPersistent": "false",
                "aws:ResourceTag/PortfolioRepository": (
                    payload["github_contract"]["repository"]
                ),
            },
            {
                "effective": "denied",
                "identity": "denied",
                "boundary": "allowed",
            },
        ),
        (
            "persistent",
            {
                "aws:ResourceTag/PortfolioEnvironment": "manual",
                "aws:ResourceTag/PortfolioManaged": "true",
                "aws:ResourceTag/PortfolioPersistent": "true",
                "aws:ResourceTag/PortfolioRepository": (
                    payload["github_contract"]["repository"]
                ),
            },
            {
                "effective": "denied",
                "identity": "denied",
                "boundary": "allowed",
            },
        ),
    )
    destroy_identity = payload["environment_identity"]["manual/destroy"]
    checked = 0
    for action, resource in resources:
        for variant, raw_context, expected_by_layer in tag_variants:
            context = resolved_context(raw_context, "manual/destroy", payload)
            decisions = {
                "effective": identity_decision(
                    destroy_identity,
                    payload["boundary"],
                    action=action,
                    resource=resource,
                    context=context,
                ),
                "identity": identity_decision(
                    destroy_identity,
                    allow_all,
                    action=action,
                    resource=resource,
                    context=context,
                ),
                "boundary": identity_decision(
                    allow_all,
                    payload["boundary"],
                    action=action,
                    resource=resource,
                    context=context,
                ),
            }
            failures = {
                layer: decision
                for layer, decision in decisions.items()
                if decision != expected_by_layer[layer]
            }
            if failures:
                raise RuntimeError(
                    "Tagged destroy ceiling failed: "
                    f"{action} {variant} expected {expected_by_layer}, got {failures}"
                )
            checked += len(decisions)
    return checked


def verify_backend_generator() -> None:
    rendered = backend_files(
        bucket="example-portfolio-111122223333-us-east-1-state",
        region="us-east-1",
        key="bootstrap/terraform.tfstate",
    )
    if "use_lockfile = true" not in rendered["backend.hcl"]:
        raise RuntimeError("Prepared backend must enable the S3 lockfile")
    if "encrypt      = true" not in rendered["backend.hcl"]:
        raise RuntimeError("Prepared backend must enable encryption")
    if any(
        token in rendered["backend.hcl"].lower()
        for token in ("access_key", "secret", "token")
    ):
        raise RuntimeError("Prepared backend may not persist credentials")
    for invalid in (
        {
            "bucket": "UPPERCASE",
            "region": "us-east-1",
            "key": "bootstrap/terraform.tfstate",
        },
        {
            "bucket": "valid-bucket",
            "region": "invalid",
            "key": "bootstrap/terraform.tfstate",
        },
        {
            "bucket": "valid-bucket",
            "region": "us-east-1",
            "key": "environments/manual/terraform.tfstate",
        },
    ):
        try:
            validate_backend_inputs(**invalid)
        except ValueError:
            continue
        raise RuntimeError(f"Backend generator accepted invalid input: {invalid}")


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


def main() -> int:
    terraform = require_command("terraform")
    tflint = require_command("tflint")

    run(
        "Check Terraform formatting",
        [terraform, "fmt", "-check", "-recursive", str(BOOTSTRAP_ROOT)],
    )
    run(
        "Initialize pinned Terraform providers without a remote backend",
        [
            terraform,
            f"-chdir={BOOTSTRAP_ROOT}",
            "init",
            "-backend=false",
            "-input=false",
            "-lockfile=readonly",
            "-no-color",
        ],
    )
    run(
        "Validate Terraform configuration",
        [terraform, f"-chdir={BOOTSTRAP_ROOT}", "validate", "-no-color"],
    )
    run(
        "Run AWS-free Terraform mock plans",
        [terraform, f"-chdir={BOOTSTRAP_ROOT}", "test", "-no-color"],
    )
    run(
        "Lint Terraform configuration",
        [
            tflint,
            f"--chdir={BOOTSTRAP_ROOT}",
            "--config",
            ".tflint.hcl",
            "--format",
            "compact",
        ],
    )

    verify_backend_generator()
    payload = terraform_payload(terraform)
    verify_policy_structure(payload)
    max_prefix_payload = terraform_payload(
        terraform,
        {
            "name_prefix": "abcdefghijklmnopqrst",
            "state_bucket_name": ("abcdefghijklmnopqrst-111122223333-us-east-1-state"),
        },
    )
    verify_policy_structure(max_prefix_payload)
    policy_structure_mutation_cases = verify_policy_structure_mutations(payload)
    delegated_pass_role_cases = verify_delegated_pass_role_ceiling(payload)
    delegated_policy_mutation_cases = verify_delegated_policy_mutation_ceiling(payload)
    tagged_destroy_cases = verify_tagged_destroy_ceiling(payload)
    operator_control_plane_cases = verify_operator_control_plane(payload)
    counts = verify_matrix(payload)

    lock_path = BOOTSTRAP_ROOT / ".terraform.lock.hcl"
    evidence = {
        "schemaVersion": 1,
        "sourceHead": source_head(),
        "terraformVersion": command_version(terraform, "version"),
        "tflintVersion": command_version(tflint, "--version"),
        "awsProviderLockSha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
        "terraformMockPlanFiles": 1,
        "policyMatrix": counts,
        "policyStructureMutationCases": policy_structure_mutation_cases,
        "delegatedPassRoleCases": delegated_pass_role_cases,
        "delegatedPolicyMutationCases": delegated_policy_mutation_cases,
        "taggedDestroyCases": tagged_destroy_cases,
        "operatorControlPlaneCases": operator_control_plane_cases,
        "policySizes": payload["policy_sizes"],
        "maxAcceptedPrefixPolicySizes": max_prefix_payload["policy_sizes"],
        "awsApiCalls": 0,
        "awsWrites": 0,
        "constructionAttempts": "0/3",
    }
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"\nAWS bootstrap static proof passed: {json.dumps(counts, sort_keys=True)}")
    print(f"Evidence: {ARTIFACT_PATH.relative_to(REPOSITORY_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"AWS bootstrap verification failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
