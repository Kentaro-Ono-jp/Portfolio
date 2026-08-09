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
  github_contract = {
    allowed_events = ["schedule", "workflow_dispatch"],
    audience = "sts.amazonaws.com",
    environment = var.github_environment,
    ref = "refs/heads/main",
    repository = var.repository_identity,
    subject = local.github_oidc_subject,
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


def terraform_payload(terraform: str) -> dict[str, Any]:
    expression = " ".join(
        line.strip() for line in POLICY_EXPRESSION.splitlines() if line.strip()
    )
    completed = subprocess.run(
        [
            terraform,
            f"-chdir={BOOTSTRAP_ROOT}",
            "console",
            "-no-color",
            f"-var-file={TFVARS_PATH}",
        ],
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


def substitute(value: str, context: dict[str, str]) -> str:
    rendered = value
    for key, replacement in context.items():
        rendered = rendered.replace(f"${{{key}}}", replacement)
    return rendered


def action_matches(requested: str, configured: Any) -> bool:
    requested_lower = requested.lower()
    return any(
        fnmatch.fnmatchcase(requested_lower, pattern.lower())
        for pattern in values(configured)
    )


def resource_matches(requested: str, configured: Any, context: dict[str, str]) -> bool:
    return any(
        fnmatch.fnmatchcase(requested, substitute(pattern, context))
        for pattern in values(configured)
    )


def condition_matches(condition: dict[str, Any], context: dict[str, str]) -> bool:
    for operator, clauses in condition.items():
        for key, expected_value in clauses.items():
            expected = [substitute(item, context) for item in values(expected_value)]
            actual = context.get(key)
            if operator in {"StringEquals", "ArnEquals", "Bool"}:
                if actual is None or actual not in expected:
                    return False
            elif operator in {"StringLike", "ArnLike"}:
                if actual is None or not any(
                    fnmatch.fnmatchcase(actual, pattern) for pattern in expected
                ):
                    return False
            elif operator in {"StringNotEquals", "ArnNotEquals"}:
                if actual is not None and actual in expected:
                    return False
            else:
                raise RuntimeError(f"Unsupported policy condition operator: {operator}")
    return True


def matching_effects(
    policy: dict[str, Any],
    *,
    action: str,
    resource: str,
    context: dict[str, str],
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
    context: dict[str, str],
) -> str:
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
    raw: dict[str, str], role: str, payload: dict[str, Any]
) -> dict[str, str]:
    context = {
        key: resolve_symbol(value, payload)
        if value in {"boundary", "admin-policy"}
        else value
        for key, value in raw.items()
    }
    context.setdefault("aws:PrincipalTag/PortfolioEnvironment", role_environment(role))
    context.setdefault("aws:PrincipalTag/PortfolioPurpose", role_purpose(role))
    return context


def verify_matrix(payload: dict[str, Any]) -> dict[str, int]:
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    if matrix.get("schemaVersion") != 1:
        raise RuntimeError("Unknown policy matrix schema")
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

    if sorted(payload["github_contract"]["allowed_events"]) != [
        "schedule",
        "workflow_dispatch",
    ]:
        raise RuntimeError("Future GitHub authority must stay event-class restricted")
    if set(payload["ecr_arns"]) != {"api", "ml", "web"}:
        raise RuntimeError(
            "ECR contract must contain independent Web, API, and ML repositories"
        )
    if len(payload["environment_identity"]) != 16:
        raise RuntimeError("Synthetic contract must expose eight roles per environment")


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
