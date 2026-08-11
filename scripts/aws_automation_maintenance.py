from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aws_lifecycle as lifecycle
from aws_lifecycle_core import LifecycleConfig
from verify_aws_static_iam import (
    CONTRACT_ROOTS,
    contract_file,
    iam_documents_equal,
    load_json,
    render_tokens,
    rendered,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE_ROOT = REPOSITORY_ROOT / "infra" / "aws" / "lifecycle"
WRITE_OPERATIONS = {
    "iam:create-open-id-connect-provider",
    "iam:create-policy",
    "iam:create-policy-version",
    "iam:delete-policy-version",
    "iam:create-role",
    "iam:update-assume-role-policy",
    "iam:attach-role-policy",
    "logs:create-log-group",
    "logs:put-retention-policy",
    "logs:tag-resource",
    "scheduler:create-schedule-group",
    "codebuild:create-project",
}


@dataclass
class Effects:
    calls: int = 0
    write_attempts: int = 0
    successful_writes: int = 0
    resources_created: int = 0
    policies_updated: int = 0
    trusts_updated: int = 0


class AwsCli:
    def __init__(self, executable: str) -> None:
        self.executable = executable
        self.effects = Effects()

    def call(
        self,
        service: str,
        operation: str,
        *arguments: str,
        allow_missing: tuple[str, ...] = (),
        creates: bool = False,
    ) -> dict[str, Any] | None:
        self.effects.calls += 1
        key = f"{service}:{operation}"
        is_write = key in WRITE_OPERATIONS
        if is_write:
            self.effects.write_attempts += 1
        result = subprocess.run(
            [
                self.executable,
                service,
                operation,
                *arguments,
                "--output",
                "json",
                "--no-cli-pager",
            ],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            if any(code in result.stderr for code in allow_missing):
                return None
            raise RuntimeError(f"AWS maintenance call failed safely: {key}")
        if is_write:
            self.effects.successful_writes += 1
            if creates:
                self.effects.resources_created += 1
        payload = json.loads(result.stdout or "{}")
        if not isinstance(payload, dict):
            raise RuntimeError(f"AWS maintenance returned invalid data: {key}")
        return payload


def tags(environment: str, repository: str, purpose: str) -> dict[str, str]:
    return {
        "PortfolioEnvironment": environment,
        "PortfolioManaged": "true",
        "PortfolioPersistent": "true",
        "PortfolioRepository": repository,
        "PortfolioPurpose": purpose,
    }


def iam_tags(value: dict[str, str]) -> str:
    return json.dumps([{"Key": key, "Value": item} for key, item in value.items()])


def codebuild_tags(value: dict[str, str]) -> list[dict[str, str]]:
    return [{"key": key, "value": item} for key, item in value.items()]


def build_contract(
    account_id: str,
    partition: str,
    region: str,
    name_prefix: str,
    repository: str,
    state_bucket: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    policies: dict[str, dict[str, Any]] = {}
    roles: dict[str, dict[str, Any]] = {}
    for environment, root in CONTRACT_ROOTS.items():
        tokens = render_tokens(
            account_id=account_id,
            partition=partition,
            region=region,
            environment=environment,
            name_prefix=name_prefix,
            repository_identity=repository,
            state_bucket_name=state_bucket,
        )
        template = load_json(root / "manifest.json")
        manifest = rendered(template, tokens)
        for key, spec in manifest["managedPolicies"].items():
            document = rendered(
                load_json(
                    contract_file(root, template["managedPolicies"][key]["document"])
                ),
                tokens,
            )
            candidate = {"name": spec["name"], "document": document}
            existing = policies.get(spec["name"])
            if existing is not None and not iam_documents_equal(
                existing["document"], document
            ):
                raise RuntimeError("Shared managed-policy contract disagrees")
            policies[spec["name"]] = candidate
        for purpose, spec in manifest["roles"].items():
            trust = rendered(
                load_json(contract_file(root, template["roles"][purpose]["trust"])),
                tokens,
            )
            candidate = {
                "name": spec["name"],
                "trust": trust,
                "permissions": [
                    manifest["managedPolicies"][key]["name"]
                    for key in spec["permissions"]
                ],
                "boundary": manifest["managedPolicies"][spec["boundary"]]["name"],
                "tags": spec["tags"],
                "purpose": purpose,
            }
            existing = roles.get(spec["name"])
            if existing is not None and existing != candidate:
                raise RuntimeError("Shared role contract disagrees")
            roles[spec["name"]] = candidate
    return policies, roles


def ensure_oidc_provider(
    aws: AwsCli,
    *,
    apply: bool,
    account_id: str,
    partition: str,
    repository: str,
) -> str:
    arn = (
        f"arn:{partition}:iam::{account_id}:"
        "oidc-provider/token.actions.githubusercontent.com"
    )
    provider = aws.call(
        "iam",
        "get-open-id-connect-provider",
        "--open-id-connect-provider-arn",
        arn,
        allow_missing=("NoSuchEntity",),
    )
    expected_tags = tags("shared", repository, "github-oidc")
    if provider is None:
        if apply:
            aws.call(
                "iam",
                "create-open-id-connect-provider",
                "--url",
                "https://token.actions.githubusercontent.com",
                "--client-id-list",
                "sts.amazonaws.com",
                "--tags",
                iam_tags(expected_tags),
                creates=True,
            )
        return "create"
    if provider.get("Url") != "token.actions.githubusercontent.com" or set(
        provider.get("ClientIDList", [])
    ) != {"sts.amazonaws.com"}:
        raise RuntimeError("Existing GitHub OIDC provider contract drifted")
    actual_tags = aws.call(
        "iam",
        "list-open-id-connect-provider-tags",
        "--open-id-connect-provider-arn",
        arn,
    ) or {"Tags": []}
    tag_map = {
        str(item["Key"]): str(item["Value"]) for item in actual_tags.get("Tags", [])
    }
    if tag_map != expected_tags:
        raise RuntimeError("Existing GitHub OIDC provider tags drifted")
    return "unchanged"


def policy_arn(partition: str, account_id: str, name: str) -> str:
    return f"arn:{partition}:iam::{account_id}:policy/{name}"


def ensure_policy(
    aws: AwsCli,
    *,
    apply: bool,
    account_id: str,
    partition: str,
    name: str,
    document: dict[str, Any],
) -> str:
    arn = policy_arn(partition, account_id, name)
    policy = aws.call(
        "iam",
        "get-policy",
        "--policy-arn",
        arn,
        allow_missing=("NoSuchEntity",),
    )
    encoded = json.dumps(document, separators=(",", ":"), sort_keys=True)
    if policy is None:
        if apply:
            aws.call(
                "iam",
                "create-policy",
                "--policy-name",
                name,
                "--policy-document",
                encoded,
                creates=True,
            )
        return "create"
    default_id = str(policy["Policy"]["DefaultVersionId"])
    version = (
        aws.call(
            "iam",
            "get-policy-version",
            "--policy-arn",
            arn,
            "--version-id",
            default_id,
        )
        or {}
    )
    actual = version.get("PolicyVersion", {}).get("Document", {})
    if iam_documents_equal(actual, document):
        return "unchanged"
    if apply:
        versions = aws.call("iam", "list-policy-versions", "--policy-arn", arn) or {
            "Versions": []
        }
        non_default = [
            item
            for item in versions.get("Versions", [])
            if not item.get("IsDefaultVersion")
        ]
        if len(versions.get("Versions", [])) >= 5 and non_default:
            oldest = min(non_default, key=lambda item: str(item.get("CreateDate", "")))
            aws.call(
                "iam",
                "delete-policy-version",
                "--policy-arn",
                arn,
                "--version-id",
                str(oldest["VersionId"]),
            )
        aws.call(
            "iam",
            "create-policy-version",
            "--policy-arn",
            arn,
            "--policy-document",
            encoded,
            "--set-as-default",
        )
        aws.effects.policies_updated += 1
    return "update"


def ensure_role(
    aws: AwsCli,
    *,
    apply: bool,
    account_id: str,
    partition: str,
    spec: dict[str, Any],
) -> str:
    name = str(spec["name"])
    role = aws.call(
        "iam", "get-role", "--role-name", name, allow_missing=("NoSuchEntity",)
    )
    boundary = policy_arn(partition, account_id, str(spec["boundary"]))
    created = role is None
    if created:
        if apply:
            aws.call(
                "iam",
                "create-role",
                "--role-name",
                name,
                "--assume-role-policy-document",
                json.dumps(spec["trust"], separators=(",", ":"), sort_keys=True),
                "--permissions-boundary",
                boundary,
                "--max-session-duration",
                "3600",
                "--tags",
                iam_tags(spec["tags"]),
                creates=True,
            )
        status = "create"
    else:
        value = role["Role"]
        if value.get("Path") != "/" or value.get("MaxSessionDuration") != 3600:
            raise RuntimeError("Existing static role shape drifted")
        if (
            value.get("PermissionsBoundary", {}).get("PermissionsBoundaryArn")
            != boundary
        ):
            raise RuntimeError("Existing static role boundary drifted")
        actual_tags = {
            str(item["Key"]): str(item["Value"]) for item in value.get("Tags", [])
        }
        if actual_tags != spec["tags"]:
            raise RuntimeError("Existing static role tags drifted")
        if not iam_documents_equal(
            value.get("AssumeRolePolicyDocument"), spec["trust"]
        ):
            if apply:
                aws.call(
                    "iam",
                    "update-assume-role-policy",
                    "--role-name",
                    name,
                    "--policy-document",
                    json.dumps(spec["trust"], separators=(",", ":"), sort_keys=True),
                )
                aws.effects.trusts_updated += 1
            status = "update"
        else:
            status = "unchanged"
    if not apply and created:
        return status
    attached = aws.call("iam", "list-attached-role-policies", "--role-name", name) or {
        "AttachedPolicies": []
    }
    actual = {str(item["PolicyArn"]) for item in attached["AttachedPolicies"]}
    expected = {
        policy_arn(partition, account_id, policy) for policy in spec["permissions"]
    }
    extra = actual - expected
    if extra:
        raise RuntimeError("Existing static role has an undeclared policy")
    if actual != expected:
        status = "update"
    inline = aws.call("iam", "list-role-policies", "--role-name", name) or {
        "PolicyNames": []
    }
    if inline.get("PolicyNames"):
        raise RuntimeError("Existing static role has an inline policy")
    for arn in sorted(expected - actual):
        if apply:
            aws.call(
                "iam",
                "attach-role-policy",
                "--role-name",
                name,
                "--policy-arn",
                arn,
            )
    return status


def role_creation_order(spec: dict[str, Any]) -> tuple[int, int, str]:
    purpose_order = {
        "operator_deployment": 0,
        "task_execution": 1,
        "web_workload": 2,
        "api_workload": 3,
        "ml_workload": 4,
        "codebuild_image": 5,
        "codebuild_destroy": 6,
        "destroy": 7,
        "scheduler": 8,
    }
    purpose = str(spec["purpose"])
    if purpose == "automation":
        return (-1, -1, str(spec["name"]))
    name = str(spec["name"])
    environment_order = 0 if "-manual-" in name else 1
    return (environment_order, purpose_order[purpose], name)


def controller_tags(repository: str, purpose: str) -> dict[str, str]:
    return {
        **tags("monthly", repository, f"{purpose}-controller"),
        "PortfolioLayer": "bootstrap",
    }


def ensure_monthly_controllers(
    aws: AwsCli,
    *,
    apply: bool,
    account_id: str,
    partition: str,
    region: str,
    name_prefix: str,
    repository: str,
    state_bucket: str,
) -> int:
    created = 0
    group_name = f"{name_prefix}-monthly-lifecycle"
    group_arn = (
        f"arn:{partition}:scheduler:{region}:{account_id}:schedule-group/{group_name}"
    )
    group = aws.call(
        "scheduler",
        "get-schedule-group",
        "--name",
        group_name,
        allow_missing=("ResourceNotFoundException",),
    )
    if group is None and apply:
        aws.call(
            "scheduler",
            "create-schedule-group",
            "--name",
            group_name,
            "--tags",
            iam_tags(
                {
                    key: value
                    for key, value in tags(
                        "monthly", repository, "lifecycle-schedule-group"
                    ).items()
                    if key != "PortfolioPurpose"
                }
            ),
            creates=True,
        )
        created += 1
    elif group is not None and group.get("Arn") != group_arn:
        raise RuntimeError("Monthly schedule group ARN drifted")

    for purpose in ("image", "destroy"):
        log_name = f"/portfolio/{name_prefix}/monthly/controller/{purpose}"
        logs = aws.call(
            "logs",
            "describe-log-groups",
            "--log-group-name-prefix",
            log_name,
        ) or {"logGroups": []}
        exact_logs = [
            item
            for item in logs.get("logGroups", [])
            if item.get("logGroupName") == log_name
        ]
        if not exact_logs and apply:
            aws.call(
                "logs", "create-log-group", "--log-group-name", log_name, creates=True
            )
            aws.call(
                "logs",
                "put-retention-policy",
                "--log-group-name",
                log_name,
                "--retention-in-days",
                "7",
            )
            log_arn = f"arn:{partition}:logs:{region}:{account_id}:log-group:{log_name}"
            aws.call(
                "logs",
                "tag-resource",
                "--resource-arn",
                log_arn,
                "--tags",
                json.dumps(controller_tags(repository, purpose)),
            )
            created += 1
        project_name = f"{name_prefix}-monthly-{purpose if purpose == 'destroy' else 'image-build'}"
        projects = aws.call(
            "codebuild", "batch-get-projects", "--names", project_name
        ) or {"projects": []}
        if not projects.get("projects") and apply:
            buildspec_name = (
                "image-build.buildspec.yml"
                if purpose == "image"
                else "destroy.buildspec.yml"
            )
            role_purpose = (
                "codebuild-image" if purpose == "image" else "codebuild-destroy"
            )
            payload = {
                "name": project_name,
                "source": {
                    "type": "NO_SOURCE",
                    "buildspec": (LIFECYCLE_ROOT / buildspec_name).read_text(
                        encoding="utf-8"
                    ),
                },
                "artifacts": {"type": "NO_ARTIFACTS"},
                "environment": {
                    "type": "LINUX_CONTAINER",
                    "image": "aws/codebuild/standard:7.0",
                    "computeType": "BUILD_GENERAL1_SMALL",
                    "imagePullCredentialsType": "CODEBUILD",
                    "privilegedMode": purpose == "image",
                    "environmentVariables": [
                        {"name": "PORTFOLIO_STATE_BUCKET", "value": state_bucket},
                        {
                            "name": "PORTFOLIO_CONFIGURATION_KEY",
                            "value": f"controls/{name_prefix}/monthly/configuration.json",
                        },
                        {
                            "name": "PORTFOLIO_DESTROY_ROLE_ARN",
                            "value": f"arn:{partition}:iam::{account_id}:role/{name_prefix}-monthly-destroy",
                        },
                        {"name": "PORTFOLIO_AWS_REGION", "value": region},
                    ],
                },
                "serviceRole": f"arn:{partition}:iam::{account_id}:role/{name_prefix}-monthly-{role_purpose}",
                "timeoutInMinutes": 60,
                "queuedTimeoutInMinutes": 30,
                "autoRetryLimit": 0 if purpose == "image" else 2,
                "logsConfig": {
                    "cloudWatchLogs": {
                        "status": "ENABLED",
                        "groupName": log_name,
                        "streamName": purpose,
                    }
                },
                "tags": codebuild_tags(controller_tags(repository, purpose)),
            }
            aws.call(
                "codebuild",
                "create-project",
                "--cli-input-json",
                json.dumps(payload, separators=(",", ":")),
                creates=True,
            )
            created += 1
    return created


def lifecycle_config(
    *,
    account_id: str,
    partition: str,
    region: str,
    name_prefix: str,
    repository: str,
    state_bucket: str,
) -> LifecycleConfig:
    environment = "monthly"
    role_base = f"arn:{partition}:iam::{account_id}:role/{name_prefix}-{environment}"
    return LifecycleConfig(
        account_id=account_id,
        partition=partition,
        region=region,
        availability_zones=(f"{region}a", f"{region}b"),
        name_prefix=name_prefix,
        environment=environment,
        repository_identity=repository,
        repository_url=f"https://github.com/{repository}.git",
        source_sha="0" * 40,
        state_bucket=state_bucket,
        state_key="environments/monthly/terraform.tfstate",
        control_prefix=f"controls/{name_prefix}/monthly",
        source_user_name="ReactorFrontNoel",
        roles={
            purpose: f"{role_base}-{purpose.replace('_', '-')}"
            for purpose in (
                "operator_deployment",
                "task_execution",
                "web_workload",
                "api_workload",
                "ml_workload",
                "scheduler",
                "codebuild_image",
                "codebuild_destroy",
                "destroy",
            )
        },
        projects={
            "image": f"{name_prefix}-monthly-image-build",
            "destroy": f"{name_prefix}-monthly-destroy",
        },
        ecr_repository_urls={
            purpose: (
                f"{account_id}.dkr.ecr.{region}.amazonaws.com/{name_prefix}/{purpose}"
            )
            for purpose in ("web", "api", "ml")
        },
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Perform the separately authorized Step 6 static maintenance"
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--owner-checkpoint")
    parser.add_argument("--aws-cli", default="aws")
    parser.add_argument("--partition", default="aws")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--name-prefix", default="reactorfront")
    parser.add_argument("--repository-identity", default="Kentaro-Ono-jp/Portfolio")
    args = parser.parse_args()
    if args.apply and args.owner_checkpoint != "issue-116":
        parser.error("--apply requires --owner-checkpoint issue-116")
    return args


def main() -> int:
    args = parse_args()
    aws = AwsCli(args.aws_cli)
    identity = aws.call("sts", "get-caller-identity") or {}
    account_id = str(identity.get("Account", ""))
    caller_arn = str(identity.get("Arn", ""))
    if len(account_id) != 12 or caller_arn.endswith(":user/ReactorFrontNoel"):
        raise RuntimeError("Static maintenance requires the owner-admin session")
    state_bucket = f"{args.name_prefix}-{account_id}-{args.region}-state"
    policies, roles = build_contract(
        account_id,
        args.partition,
        args.region,
        args.name_prefix,
        args.repository_identity,
        state_bucket,
    )
    statuses = {"create": 0, "update": 0, "unchanged": 0}
    oidc_status = ensure_oidc_provider(
        aws,
        apply=args.apply,
        account_id=account_id,
        partition=args.partition,
        repository=args.repository_identity,
    )
    statuses[oidc_status] += 1
    for spec in policies.values():
        status = ensure_policy(
            aws,
            apply=args.apply,
            account_id=account_id,
            partition=args.partition,
            name=spec["name"],
            document=spec["document"],
        )
        statuses[status] += 1
    ordered_roles = sorted(roles.values(), key=role_creation_order)
    for spec in ordered_roles:
        status = ensure_role(
            aws,
            apply=args.apply,
            account_id=account_id,
            partition=args.partition,
            spec=spec,
        )
        statuses[status] += 1
    controller_creates = ensure_monthly_controllers(
        aws,
        apply=args.apply,
        account_id=account_id,
        partition=args.partition,
        region=args.region,
        name_prefix=args.name_prefix,
        repository=args.repository_identity,
        state_bucket=state_bucket,
    )
    if args.apply:
        if (
            ensure_oidc_provider(
                aws,
                apply=False,
                account_id=account_id,
                partition=args.partition,
                repository=args.repository_identity,
            )
            != "unchanged"
        ):
            raise RuntimeError("GitHub OIDC provider read-back drifted")
        for spec in policies.values():
            if (
                ensure_policy(
                    aws,
                    apply=False,
                    account_id=account_id,
                    partition=args.partition,
                    name=spec["name"],
                    document=spec["document"],
                )
                != "unchanged"
            ):
                raise RuntimeError("Static policy post-write read-back drifted")
        for spec in ordered_roles:
            if (
                ensure_role(
                    aws,
                    apply=False,
                    account_id=account_id,
                    partition=args.partition,
                    spec=spec,
                )
                != "unchanged"
            ):
                raise RuntimeError("Static role post-write read-back drifted")
        config = lifecycle_config(
            account_id=account_id,
            partition=args.partition,
            region=args.region,
            name_prefix=args.name_prefix,
            repository=args.repository_identity,
            state_bucket=state_bucket,
        )
        reader = lifecycle.AwsCli(args.aws_cli)
        lifecycle.verify_controller(config, reader)
        lifecycle.verify_image_repositories(config, reader)
        lifecycle.verify_state_bucket(config, reader)
        controller_readback = True
    else:
        controller_readback = False
    result = {
        "mode": "apply" if args.apply else "plan",
        "contractProfiles": 2,
        "managedPolicies": len(policies),
        "persistentRoles": len(roles),
        "plannedCreates": statuses["create"],
        "plannedUpdates": statuses["update"],
        "unchangedObjects": statuses["unchanged"],
        "controllerResourcesCreated": controller_creates,
        "controllerReadback": controller_readback,
        "postWriteReadback": args.apply,
        "awsCalls": aws.effects.calls,
        "awsWriteAttempts": aws.effects.write_attempts,
        "awsSuccessfulWrites": aws.effects.successful_writes,
        "awsTrackedCreates": aws.effects.resources_created,
        "policyDocumentsUpdated": aws.effects.policies_updated,
        "trustDocumentsUpdated": aws.effects.trusts_updated,
        "accountSpecificValuesPublished": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (json.JSONDecodeError, OSError, RuntimeError) as error:
        print(f"AWS automation maintenance failed safely: {error}", file=sys.stderr)
        raise SystemExit(1) from error
