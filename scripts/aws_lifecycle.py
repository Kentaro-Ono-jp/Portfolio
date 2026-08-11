from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import string
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from aws_automation_contract import EXPECTED_IMMUTABLE_REPOSITORY_SUBJECT
from aws_lifecycle_core import (
    CALLER_MODE_GITHUB_AUTOMATION,
    CALLER_MODE_SOURCE_USER,
    DIGEST_PATTERN,
    LifecycleConfig,
    LifecycleError,
    LifecycleState,
    Phase,
    accepted_repository_remotes,
    assert_public_safe,
    canonical_json,
    isoformat,
    parse_time,
    sanitized_status,
    sha256_file,
    sha256_json,
    utc_now,
    validate_fallback_window,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE_ROOT = REPOSITORY_ROOT / "infra" / "aws" / "lifecycle"
TERRAFORM_VERSION = "1.15.8"
SOURCE_USER_NAME = "ReactorFrontNoel"
DEFAULT_REPOSITORY = "Kentaro-Ono-jp/Portfolio"
DEFAULT_PREFIX = "reactorfront"
DEFAULT_ENVIRONMENT = "manual"
DEFAULT_REGION = "us-east-1"
BUILD_TIMEOUT_SECONDS = 3600
PLAN_MAX_AGE_SECONDS = 1800
SEED_OWNER_LENGTH = 64


WRITE_OPERATIONS = {
    "s3api:put-object",
    "s3api:delete-object",
    "codebuild:start-build",
    "codebuild:update-project",
    "scheduler:create-schedule",
    "scheduler:update-schedule",
    "scheduler:delete-schedule",
    "ecs:run-task",
    "ecs:stop-task",
    "ecr:batch-delete-image",
    "cognito-idp:admin-create-user",
    "cognito-idp:admin-set-user-password",
    "cognito-idp:admin-add-user-to-group",
    "cognito-idp:admin-delete-user",
}


@dataclass
class Effects:
    calls: int = 0
    write_attempts: int = 0
    successful_writes: int = 0
    resources_created: int = 0

    def add(self, other: Effects) -> None:
        self.calls += other.calls
        self.write_attempts += other.write_attempts
        self.successful_writes += other.successful_writes
        self.resources_created += other.resources_created

    def result(self) -> dict[str, object]:
        return {
            "effectScope": "direct-aws-cli-wrapper-only",
            "directAwsCliCalls": self.calls,
            "directAwsCliWriteAttempts": self.write_attempts,
            "directAwsCliSuccessfulWrites": self.successful_writes,
            "directAwsCliTrackedCreates": self.resources_created,
            "terraformProviderAndControllerEffectsIncluded": False,
        }


class AwsCli:
    def __init__(
        self, executable: str, *, env: Mapping[str, str] | None = None
    ) -> None:
        self.executable = executable
        self.env = dict(os.environ if env is None else env)
        self.effects = Effects()

    def call(
        self,
        service: str,
        operation: str,
        *arguments: str,
        allow_error_codes: Sequence[str] = (),
        resource_delta: int = 0,
    ) -> dict[str, Any] | None:
        self.effects.calls += 1
        key = f"{service}:{operation}"
        if key in WRITE_OPERATIONS:
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
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            if any(code in result.stderr for code in allow_error_codes):
                return None
            raise LifecycleError(f"AWS call failed safely: {service} {operation}.")
        try:
            value = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as error:
            raise LifecycleError(
                f"AWS call returned invalid JSON: {service} {operation}."
            ) from error
        if not isinstance(value, dict):
            raise LifecycleError(
                f"AWS call returned a non-object: {service} {operation}."
            )
        if key in WRITE_OPERATIONS:
            self.effects.successful_writes += 1
            self.effects.resources_created += resource_delta
        return value

    def wait(self, service: str, waiter: str, *arguments: str) -> None:
        self.effects.calls += 1
        result = subprocess.run(
            [
                self.executable,
                service,
                "wait",
                waiter,
                *arguments,
                "--no-cli-pager",
            ],
            cwd=REPOSITORY_ROOT,
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise LifecycleError(f"AWS waiter failed safely: {service} {waiter}.")


def run_process(
    command: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    timeout: int | None = None,
    label: str,
    safe_failure_prefix: str | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(command),
        cwd=REPOSITORY_ROOT,
        env=None if env is None else dict(env),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        retain_private_process_diagnostic(label, result)
        safe_detail = public_process_failure_detail(result, safe_failure_prefix)
        if safe_detail:
            raise LifecycleError(f"{label} failed safely: {safe_detail}")
        raise LifecycleError(f"{label} failed; private diagnostics were retained.")
    return result


def public_process_failure_detail(
    result: subprocess.CompletedProcess[str], prefix: str | None
) -> str | None:
    if not prefix:
        return None
    for line in reversed((result.stderr or "").splitlines()):
        candidate = " ".join(line.split())
        if not candidate.startswith(prefix) or len(candidate) > 500:
            continue
        try:
            assert_public_safe({"processFailure": candidate})
        except LifecycleError:
            continue
        return candidate
    return None


def retain_private_process_diagnostic(
    label: str, result: subprocess.CompletedProcess[str]
) -> None:
    git_root = REPOSITORY_ROOT / ".git"
    if not git_root.is_dir():
        return
    safe_label = "".join(
        character.lower() if character.isalnum() else "-" for character in label
    ).strip("-")
    while "--" in safe_label:
        safe_label = safe_label.replace("--", "-")
    path = (
        git_root
        / "portfolio-aws-lifecycle"
        / "private-diagnostics"
        / (f"{safe_label or 'process'}.log")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "STDOUT\n" + (result.stdout or "") + "\nSTDERR\n" + (result.stderr or ""),
        encoding="utf-8",
    )
    try:
        path.chmod(0o600)
    except OSError:
        pass


def require_command(command: str) -> str:
    resolved = shutil.which(command)
    if resolved is None:
        raise LifecycleError(f"Required command is unavailable: {command}.")
    return resolved


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LifecycleError(
            "Lifecycle JSON input is unavailable or invalid."
        ) from error
    if not isinstance(value, dict):
        raise LifecycleError("Lifecycle JSON input must be an object.")
    return value


def write_private_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    try:
        path.chmod(0o600)
    except OSError:
        pass


def aws_account_suffix(partition: str) -> str:
    return "amazonaws.com.cn" if partition == "aws-cn" else "amazonaws.com"


def role_arn(config: LifecycleConfig, purpose: str) -> str:
    return config.roles[purpose]


def project_arn(config: LifecycleConfig, purpose: str) -> str:
    return (
        f"arn:{config.partition}:codebuild:{config.region}:{config.account_id}:"
        f"project/{config.projects[purpose]}"
    )


def source_user_arn(config: LifecycleConfig) -> str:
    return (
        f"arn:{config.partition}:iam::{config.account_id}:user/"
        f"{config.source_user_name}"
    )


def automation_session_pattern(config: LifecycleConfig) -> re.Pattern[str]:
    return re.compile(
        rf"^arn:{re.escape(config.partition)}:sts::{re.escape(config.account_id)}:"
        rf"assumed-role/{re.escape(config.name_prefix)}-automation/"
        r"portfolio-github-[0-9]+$"
    )


def derive_config(args: argparse.Namespace, source: AwsCli) -> LifecycleConfig:
    identity = source.call("sts", "get-caller-identity") or {}
    account_id = str(identity.get("Account", ""))
    partition = "aws"
    source_arn = str(identity.get("Arn", ""))
    expected_source = f"arn:{partition}:iam::{account_id}:user/{SOURCE_USER_NAME}"
    if args.caller_mode == CALLER_MODE_SOURCE_USER:
        if source_arn != expected_source:
            raise LifecycleError(
                "Active credential is not the exact Portfolio source user."
            )
    elif args.caller_mode == CALLER_MODE_GITHUB_AUTOMATION:
        expected_automation = re.compile(
            rf"^arn:{partition}:sts::{re.escape(account_id)}:assumed-role/"
            rf"{re.escape(args.name_prefix)}-automation/portfolio-github-[0-9]+$"
        )
        if expected_automation.fullmatch(source_arn) is None:
            raise LifecycleError(
                "Active credential is not the exact GitHub automation session."
            )
    else:
        raise LifecycleError("Unsupported lifecycle caller mode.")
    source_sha = run_process(
        ["git", "rev-parse", "HEAD"], label="Git source identity"
    ).stdout.strip()
    repository_identity = args.repository_identity
    prefix = args.name_prefix
    environment = args.environment
    region = args.region
    state_bucket = args.state_bucket or f"{prefix}-{account_id}-{region}-state"
    role_base = f"arn:{partition}:iam::{account_id}:role/{prefix}-{environment}"
    repositories = {
        purpose: (
            f"{account_id}.dkr.ecr.{region}.{aws_account_suffix(partition)}/"
            f"{prefix}/{purpose}"
        )
        for purpose in ("web", "api", "ml")
    }
    return LifecycleConfig(
        account_id=account_id,
        partition=partition,
        region=region,
        availability_zones=tuple(args.availability_zones),
        name_prefix=prefix,
        environment=environment,
        repository_identity=repository_identity,
        repository_url=f"https://github.com/{repository_identity}.git",
        source_sha=source_sha,
        state_bucket=state_bucket,
        state_key=f"environments/{environment}/terraform.tfstate",
        control_prefix=f"controls/{prefix}/{environment}",
        source_user_name=SOURCE_USER_NAME,
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
            "image": f"{prefix}-{environment}-image-build",
            "destroy": f"{prefix}-{environment}-destroy",
        },
        ecr_repository_urls=repositories,
        caller_mode=args.caller_mode,
        caller_event=args.automation_event,
        oidc_api_audience=args.oidc_api_audience,
    )


def load_config(path: Path) -> LifecycleConfig:
    return LifecycleConfig.from_dict(load_json(path))


def verify_local_source(config: LifecycleConfig, *, require_remote: bool) -> None:
    status = run_process(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        label="Git cleanliness check",
    ).stdout
    tracked_or_untracked = [
        line for line in status.splitlines() if ".git/" not in line.replace("\\", "/")
    ]
    if tracked_or_untracked:
        raise LifecycleError("The repository worktree is not clean.")
    head = run_process(
        ["git", "rev-parse", "HEAD"], label="Git HEAD check"
    ).stdout.strip()
    if head != config.source_sha:
        raise LifecycleError("The configured source SHA is not the exact local HEAD.")
    remote = run_process(
        ["git", "remote", "get-url", "origin"], label="Git remote check"
    ).stdout.strip()
    accepted = accepted_repository_remotes(config.repository_identity)
    if remote not in accepted:
        raise LifecycleError("The Git remote does not match repositoryIdentity.")
    if require_remote:
        refs = run_process(
            ["git", "ls-remote", "origin"],
            timeout=60,
            label="Published source check",
        ).stdout
        if not any(
            line.startswith(f"{config.source_sha}\t") for line in refs.splitlines()
        ):
            raise LifecycleError(
                "The exact source SHA is not published on the public remote."
            )


def assume_role(
    caller: AwsCli,
    config: LifecycleConfig,
    purpose: str,
    session_name: str,
) -> AwsCli:
    assumed = (
        caller.call(
            "sts",
            "assume-role",
            "--role-arn",
            role_arn(config, purpose),
            "--role-session-name",
            session_name,
            "--duration-seconds",
            "3600",
        )
        or {}
    )
    credentials = assumed.get("Credentials")
    if not isinstance(credentials, dict):
        raise LifecycleError("AssumeRole did not return credentials.")
    required = ("AccessKeyId", "SecretAccessKey", "SessionToken")
    if any(not isinstance(credentials.get(key), str) for key in required):
        raise LifecycleError("AssumeRole returned an incomplete credential set.")
    env = dict(os.environ)
    env.update(
        {
            "AWS_ACCESS_KEY_ID": credentials["AccessKeyId"],
            "AWS_SECRET_ACCESS_KEY": credentials["SecretAccessKey"],
            "AWS_SESSION_TOKEN": credentials["SessionToken"],
            "AWS_DEFAULT_REGION": config.region,
            "AWS_REGION": config.region,
        }
    )
    session = AwsCli(caller.executable, env=env)
    identity = session.call("sts", "get-caller-identity") or {}
    expected = (
        f"arn:{config.partition}:sts::{config.account_id}:assumed-role/"
        f"{config.name_prefix}-{config.environment}-{purpose.replace('_', '-')}/"
    )
    if not str(identity.get("Arn", "")).startswith(expected):
        raise LifecycleError(
            "Assumed session identity is not the exact requested role."
        )
    return session


def verify_source(config: LifecycleConfig, source: AwsCli) -> None:
    identity = source.call("sts", "get-caller-identity") or {}
    arn = str(identity.get("Arn", ""))
    if config.caller_mode == CALLER_MODE_SOURCE_USER:
        accepted = arn == source_user_arn(config)
    elif config.caller_mode == CALLER_MODE_GITHUB_AUTOMATION:
        accepted = automation_session_pattern(config).fullmatch(arn) is not None
    else:
        accepted = False
    if not accepted:
        raise LifecycleError(
            "Active credential does not match the configured lifecycle caller."
        )


def verify_static_iam(config: LifecycleConfig, aws_executable: str) -> dict[str, Any]:
    result = run_process(
        [
            sys.executable,
            "scripts/verify_aws_static_iam.py",
            "--live",
            "--aws-cli",
            aws_executable,
            "--account-id",
            config.account_id,
            "--partition",
            config.partition,
            "--region",
            config.region,
            "--name-prefix",
            config.name_prefix,
            "--environment",
            config.environment,
            "--repository-identity",
            config.repository_identity,
            "--github-oidc-repository-subject",
            EXPECTED_IMMUTABLE_REPOSITORY_SUBJECT,
            "--state-bucket-name",
            config.state_bucket,
            "--caller-mode",
            config.caller_mode,
        ],
        timeout=300,
        label="Frozen static IAM attestation",
        safe_failure_prefix="Static IAM verification failed:",
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise LifecycleError(
            "Static IAM attestation returned invalid evidence."
        ) from error
    if (
        payload.get("drift") is not False
        or payload.get("attestationAwsWriteCalls") != 0
    ):
        raise LifecycleError("Frozen static IAM attestation did not pass read-only.")
    return payload


def expected_project_environment(config: LifecycleConfig) -> dict[str, str]:
    return {
        "PORTFOLIO_STATE_BUCKET": config.state_bucket,
        "PORTFOLIO_CONFIGURATION_KEY": config.configuration_key,
        "PORTFOLIO_DESTROY_ROLE_ARN": config.roles["destroy"],
        "PORTFOLIO_AWS_REGION": config.region,
    }


def normalized_buildspec(value: str) -> str:
    return value.replace("\r\n", "\n").strip()


def buildspec_digest(value: str) -> str:
    return (
        "sha256:"
        + hashlib.sha256(normalized_buildspec(value).encode("utf-8")).hexdigest()
    )


def verify_controller_projects(
    config: LifecycleConfig,
    operator: AwsCli,
    *,
    reconcile_image_buildspec: bool = False,
) -> dict[str, object]:
    response = (
        operator.call(
            "codebuild",
            "batch-get-projects",
            "--names",
            config.projects["image"],
            config.projects["destroy"],
        )
        or {}
    )
    projects = response.get("projects")
    if not isinstance(projects, list) or len(projects) != 2:
        raise LifecycleError("Persistent CodeBuild controller inventory is incomplete.")
    by_name = {str(project.get("name")): project for project in projects}
    expected_environment = expected_project_environment(config)
    image_reconciliation: dict[str, object] | None = None
    for purpose in ("image", "destroy"):
        project = by_name.get(config.projects[purpose])
        if not isinstance(project, dict):
            raise LifecycleError(f"Persistent {purpose} project is missing.")
        source = project.get("source", {})
        artifacts = project.get("artifacts", {})
        environment = project.get("environment", {})
        logs = project.get("logsConfig", {}).get("cloudWatchLogs", {})
        role_purpose = "codebuild_image" if purpose == "image" else "codebuild_destroy"
        buildspec_name = (
            "image-build.buildspec.yml"
            if purpose == "image"
            else "destroy.buildspec.yml"
        )
        expected_buildspec = (LIFECYCLE_ROOT / buildspec_name).read_text(
            encoding="utf-8"
        )
        expected_log_group = (
            f"/portfolio/{config.name_prefix}/{config.environment}/controller/{purpose}"
        )
        current_buildspec = str(source.get("buildspec", ""))
        if (
            project.get("serviceRole") != role_arn(config, role_purpose)
            or source.get("type") != "NO_SOURCE"
            or artifacts.get("type") != "NO_ARTIFACTS"
            or project.get("timeoutInMinutes") != 60
            or project.get("queuedTimeoutInMinutes") != 30
            or project.get("autoRetryLimit") != (0 if purpose == "image" else 2)
            or environment.get("computeType") != "BUILD_GENERAL1_SMALL"
            or environment.get("image") != "aws/codebuild/standard:7.0"
            or environment.get("type") != "LINUX_CONTAINER"
            or environment.get("imagePullCredentialsType") != "CODEBUILD"
            or bool(environment.get("privilegedMode")) != (purpose == "image")
            or logs.get("status") != "ENABLED"
            or logs.get("groupName") != expected_log_group
            or logs.get("streamName") != purpose
        ):
            raise LifecycleError(f"Persistent {purpose} project contract drifted.")
        variables = {
            str(item.get("name")): str(item.get("value"))
            for item in environment.get("environmentVariables", [])
            if isinstance(item, dict)
        }
        if variables != expected_environment:
            raise LifecycleError(f"Persistent {purpose} project inputs drifted.")
        tag_map = {
            str(item.get("key")): str(item.get("value"))
            for item in project.get("tags", [])
            if isinstance(item, dict)
        }
        expected_tags = {
            "PortfolioEnvironment": config.environment,
            "PortfolioLayer": "bootstrap",
            "PortfolioManaged": "true",
            "PortfolioPersistent": "true",
            "PortfolioPurpose": f"{purpose}-controller",
            "PortfolioRepository": config.repository_identity,
        }
        if tag_map != expected_tags:
            raise LifecycleError(f"Persistent {purpose} project tags drifted.")
        if normalized_buildspec(current_buildspec) == normalized_buildspec(
            expected_buildspec
        ):
            continue
        if purpose != "image" or not reconcile_image_buildspec:
            raise LifecycleError(f"Persistent {purpose} project contract drifted.")
        image_reconciliation = {
            "previousBuildspecSha256": buildspec_digest(current_buildspec),
            "currentBuildspecSha256": buildspec_digest(expected_buildspec),
        }

    if image_reconciliation is not None:
        expected_buildspec = (LIFECYCLE_ROOT / "image-build.buildspec.yml").read_text(
            encoding="utf-8"
        )
        operator.call(
            "codebuild",
            "update-project",
            "--name",
            config.projects["image"],
            "--source",
            canonical_json({"type": "NO_SOURCE", "buildspec": expected_buildspec}),
        )
        try:
            verify_controller_projects(config, operator)
        except LifecycleError as error:
            raise LifecycleError(
                "Image project reconciliation did not preserve the exact contract."
            ) from error

    return {
        "imageBuildspecReconciled": image_reconciliation is not None,
        **(image_reconciliation or {}),
    }


def verify_controller(
    config: LifecycleConfig,
    operator: AwsCli,
    *,
    reconcile_image_buildspec: bool = False,
) -> dict[str, object]:
    project_evidence = verify_controller_projects(
        config,
        operator,
        reconcile_image_buildspec=reconcile_image_buildspec,
    )
    log_prefix = f"/portfolio/{config.name_prefix}/{config.environment}/controller/"
    log_response = (
        operator.call(
            "logs",
            "describe-log-groups",
            "--log-group-name-prefix",
            log_prefix,
        )
        or {}
    )
    log_groups = [
        group
        for group in log_response.get("logGroups", [])
        if isinstance(group, dict)
        and str(group.get("logGroupName", "")).startswith(log_prefix)
    ]
    expected_log_names = {f"{log_prefix}{purpose}" for purpose in ("image", "destroy")}
    if {str(group.get("logGroupName")) for group in log_groups} != expected_log_names:
        raise LifecycleError("Persistent controller log inventory drifted.")
    for group in log_groups:
        if group.get("retentionInDays") != 7:
            raise LifecycleError("Persistent controller log retention drifted.")
        log_arn = str(group.get("arn") or group.get("logGroupArn", "")).removesuffix(
            ":*"
        )
        tags = (
            operator.call("logs", "list-tags-for-resource", "--resource-arn", log_arn)
            or {}
        ).get("tags", {})
        purpose = str(group.get("logGroupName", "")).rsplit("/", maxsplit=1)[-1]
        expected_tags = {
            "PortfolioEnvironment": config.environment,
            "PortfolioLayer": "bootstrap",
            "PortfolioManaged": "true",
            "PortfolioPersistent": "true",
            "PortfolioPurpose": f"{purpose}-controller",
            "PortfolioRepository": config.repository_identity,
        }
        if tags != expected_tags:
            raise LifecycleError("Persistent controller log tags drifted.")

    schedule_group = (
        operator.call(
            "scheduler",
            "get-schedule-group",
            "--name",
            config.schedule_group_name,
        )
        or {}
    )
    expected_group_arn = (
        f"arn:{config.partition}:scheduler:{config.region}:{config.account_id}:"
        f"schedule-group/{config.schedule_group_name}"
    )
    if (
        schedule_group.get("Arn") != expected_group_arn
        or schedule_group.get("State") != "ACTIVE"
    ):
        raise LifecycleError("Persistent lifecycle schedule group drifted.")
    schedule_group_tags = (
        operator.call(
            "scheduler",
            "list-tags-for-resource",
            "--resource-arn",
            expected_group_arn,
        )
        or {}
    )
    expected_group_tags = {
        "PortfolioEnvironment": config.environment,
        "PortfolioManaged": "true",
        "PortfolioPersistent": "true",
        "PortfolioRepository": config.repository_identity,
    }
    actual_group_tags = {
        str(item.get("Key")): str(item.get("Value"))
        for item in schedule_group_tags.get("Tags", [])
        if isinstance(item, dict)
    }
    if any(
        actual_group_tags.get(key) != value
        for key, value in expected_group_tags.items()
    ):
        raise LifecycleError("Persistent lifecycle schedule group tags drifted.")
    return project_evidence


def verify_image_repositories(config: LifecycleConfig, operator: AwsCli) -> None:
    names = [f"{config.name_prefix}/{purpose}" for purpose in ("web", "api", "ml")]
    response = (
        operator.call(
            "ecr",
            "describe-repositories",
            "--repository-names",
            *names,
        )
        or {}
    )
    repositories = response.get("repositories", [])
    if not isinstance(repositories, list) or len(repositories) != 3:
        raise LifecycleError("Persistent ECR repository inventory is incomplete.")
    by_name = {str(item.get("repositoryName")): item for item in repositories}
    for purpose in ("web", "api", "ml"):
        name = f"{config.name_prefix}/{purpose}"
        repository = by_name.get(name)
        expected_url = config.ecr_repository_urls[purpose]
        encryption = repository.get("encryptionConfiguration", {}) if repository else {}
        scanning = (
            repository.get("imageScanningConfiguration", {}) if repository else {}
        )
        if (
            not isinstance(repository, dict)
            or repository.get("repositoryUri") != expected_url
            or repository.get("imageTagMutability") != "IMMUTABLE"
            or encryption.get("encryptionType") != "AES256"
            or scanning.get("scanOnPush") is not True
        ):
            raise LifecycleError(f"Persistent {purpose} ECR contract drifted.")
        lifecycle = (
            operator.call(
                "ecr",
                "get-lifecycle-policy",
                "--repository-name",
                name,
            )
            or {}
        )
        try:
            policy = json.loads(str(lifecycle.get("lifecyclePolicyText", "")))
        except json.JSONDecodeError as error:
            raise LifecycleError(
                "Persistent ECR lifecycle policy was invalid."
            ) from error
        rules = policy.get("rules", []) if isinstance(policy, dict) else []
        if not isinstance(rules, list) or len(rules) != 2:
            raise LifecycleError("Persistent ECR lifecycle policy drifted.")
        by_priority = {
            int(rule.get("rulePriority", 0)): rule
            for rule in rules
            if isinstance(rule, dict)
        }
        if (
            by_priority.get(1, {}).get("selection")
            != {
                "tagStatus": "untagged",
                "countType": "sinceImagePushed",
                "countUnit": "days",
                "countNumber": 7,
            }
            or by_priority.get(2, {}).get("selection")
            != {
                "tagStatus": "tagged",
                "tagPatternList": ["*"],
                "countType": "imageCountMoreThan",
                "countNumber": 20,
            }
            or any(rule.get("action") != {"type": "expire"} for rule in rules)
        ):
            raise LifecycleError("Persistent ECR lifecycle retention drifted.")


def verify_state_bucket(config: LifecycleConfig, operator: AwsCli) -> None:
    location = (
        operator.call("s3api", "get-bucket-location", "--bucket", config.state_bucket)
        or {}
    ).get("LocationConstraint")
    normalized_location = "us-east-1" if location in {None, ""} else str(location)
    if normalized_location != config.region:
        raise LifecycleError("Persistent state bucket region drifted.")
    versioning = (
        operator.call("s3api", "get-bucket-versioning", "--bucket", config.state_bucket)
        or {}
    )
    if versioning.get("Status") != "Enabled":
        raise LifecycleError("Persistent state bucket versioning drifted.")
    public_access = (
        operator.call(
            "s3api", "get-public-access-block", "--bucket", config.state_bucket
        )
        or {}
    ).get("PublicAccessBlockConfiguration", {})
    required_public_blocks = {
        "BlockPublicAcls",
        "IgnorePublicAcls",
        "BlockPublicPolicy",
        "RestrictPublicBuckets",
    }
    if any(public_access.get(key) is not True for key in required_public_blocks):
        raise LifecycleError("Persistent state bucket public-access block drifted.")
    encryption = (
        operator.call("s3api", "get-bucket-encryption", "--bucket", config.state_bucket)
        or {}
    ).get("ServerSideEncryptionConfiguration", {})
    rules = encryption.get("Rules", []) if isinstance(encryption, dict) else []
    algorithms = {
        str(rule.get("ApplyServerSideEncryptionByDefault", {}).get("SSEAlgorithm"))
        for rule in rules
        if isinstance(rule, dict)
    }
    if algorithms != {"AES256"}:
        raise LifecycleError("Persistent state bucket encryption drifted.")


def runtime_directory(config_path: Path) -> Path:
    path = (config_path.parent / "runtime").resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def seed_operation_lock(config_path: Path) -> Iterator[None]:
    """Serialize seed recovery within one checkout; remote CAS covers other hosts."""
    lock_path = runtime_directory(config_path) / "seed-operation.lock"
    with lock_path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise LifecycleError(
                "Another local seed invocation owns this lifecycle operation."
            ) from error
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def s3_get_json(
    client: AwsCli,
    config: LifecycleConfig,
    key: str,
    destination: Path,
    *,
    allow_missing: bool = False,
) -> tuple[dict[str, Any], str] | None:
    response = client.call(
        "s3api",
        "get-object",
        "--bucket",
        config.state_bucket,
        "--key",
        key,
        str(destination),
        allow_error_codes=("NoSuchKey", "Not Found") if allow_missing else (),
    )
    if response is None:
        return None
    payload = load_json(destination)
    etag = str(response.get("ETag", "")).strip('"')
    if not etag:
        raise LifecycleError("Remote lifecycle object omitted its ETag.")
    return payload, etag


def s3_put_json(
    client: AwsCli,
    config: LifecycleConfig,
    key: str,
    value: object,
    source: Path,
    *,
    if_none_match: bool = False,
    if_match: str | None = None,
    resource_delta: int = 0,
) -> str:
    write_private_json(source, value)
    arguments = [
        "--bucket",
        config.state_bucket,
        "--key",
        key,
        "--body",
        str(source),
        "--server-side-encryption",
        "AES256",
        "--content-type",
        "application/json",
    ]
    if if_none_match:
        arguments.extend(["--if-none-match", "*"])
    if if_match is not None:
        arguments.extend(["--if-match", if_match])
    client.call(
        "s3api",
        "put-object",
        *arguments,
        resource_delta=resource_delta,
    )
    head = (
        client.call(
            "s3api",
            "head-object",
            "--bucket",
            config.state_bucket,
            "--key",
            key,
        )
        or {}
    )
    etag = str(head.get("ETag", "")).strip('"')
    if not etag:
        raise LifecycleError("Remote lifecycle object write could not be read back.")
    return etag


def validate_lease_payload(payload: Mapping[str, Any], config: LifecycleConfig) -> None:
    if (
        set(payload) != {"schemaVersion", "deploymentId", "acquiredAt"}
        or payload.get("schemaVersion") != 1
        or payload.get("deploymentId") != config.source_sha
    ):
        raise LifecycleError("Lifecycle lease is foreign or malformed.")
    parse_time(str(payload.get("acquiredAt", "")))


def read_remote_state(
    client: AwsCli,
    config: LifecycleConfig,
    config_path: Path,
    *,
    allow_missing: bool = False,
) -> tuple[LifecycleState, str] | None:
    result = s3_get_json(
        client,
        config,
        config.configuration_key,
        runtime_directory(config_path) / "remote-configuration.json",
        allow_missing=allow_missing,
    )
    if result is None:
        return None
    payload, etag = result
    remote_config, state = LifecycleState.from_dict(payload)
    if remote_config != config:
        raise LifecycleError("Remote lifecycle is bound to a different configuration.")
    lease = s3_get_json(
        client,
        config,
        config.lease_key,
        runtime_directory(config_path) / "remote-lease.json",
        allow_missing=True,
    )
    if lease is None:
        if not (
            state.phase == Phase.ZERO_RESIDUE
            and state.checkpoints.get("residue") == "zero"
        ):
            raise LifecycleError("Remote lifecycle checkpoint has no exact lease.")
    else:
        validate_lease_payload(lease[0], config)
    return state, etag


def write_remote_state(
    client: AwsCli,
    config: LifecycleConfig,
    config_path: Path,
    state: LifecycleState,
    *,
    if_none_match: bool = False,
    if_match: str | None = None,
) -> str:
    return s3_put_json(
        client,
        config,
        config.configuration_key,
        state.to_dict(config),
        runtime_directory(config_path) / "configuration-upload.json",
        if_none_match=if_none_match,
        if_match=if_match,
        resource_delta=1 if if_none_match else 0,
    )


def terraform_environment(config: LifecycleConfig, session: AwsCli) -> dict[str, str]:
    env = dict(session.env)
    env["TF_IN_AUTOMATION"] = "1"
    env["TF_INPUT"] = "0"
    env["TF_CLI_ARGS"] = "-no-color"
    return env


def terraform_files(
    config: LifecycleConfig, state: LifecycleState, config_path: Path
) -> tuple[Path, Path, Path, Path]:
    if set(state.images) != {"web", "api", "ml"}:
        raise LifecycleError("Terraform inputs require three immutable image digests.")
    root = runtime_directory(config_path)
    runtime_aws_root = root / "infra" / "aws"
    shutil.copytree(
        REPOSITORY_ROOT / "infra" / "aws",
        runtime_aws_root,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(".terraform", "*.tfplan", "evidence"),
    )
    environment_root = runtime_aws_root / "environment"
    write_private_json(
        environment_root / "issue114.backend.tf.json",
        {"terraform": {"backend": {"s3": {}}}},
    )
    backend = root / "backend.hcl"
    backend.write_text(
        "\n".join(
            (
                f'bucket = "{config.state_bucket}"',
                f'key = "{config.state_key}"',
                f'region = "{config.region}"',
                "encrypt = true",
                "use_lockfile = true",
                "",
            )
        ),
        encoding="utf-8",
    )
    tfvars = root / "environment.auto.tfvars.json"
    write_private_json(
        tfvars,
        {
            "aws_account_id": config.account_id,
            "aws_partition": config.partition,
            "aws_region": config.region,
            "availability_zones": list(config.availability_zones),
            "name_prefix": config.name_prefix,
            "repository_identity": config.repository_identity,
            "environment": config.environment,
            "environment_state_key": config.state_key,
            "bootstrap_role_arns": {
                key: config.roles[key]
                for key in (
                    "operator_deployment",
                    "task_execution",
                    "web_workload",
                    "api_workload",
                    "ml_workload",
                    "destroy",
                )
            },
            "ecr_repository_urls": dict(config.ecr_repository_urls),
            "image_digests": dict(state.images),
            "vpc_cidr": config.vpc_cidr,
            "public_task_subnet_cidrs": ["10.42.0.0/24", "10.42.1.0/24"],
            "isolated_service_subnet_cidrs": ["10.42.10.0/24", "10.42.11.0/24"],
            "rds_instance_class": config.rds_instance_class,
            "mq_instance_type": config.mq_instance_type,
            "log_retention_days": config.log_retention_days,
            "object_expiration_days": config.object_expiration_days,
            "reviewer_group_name": config.reviewer_group_name,
            "oidc_api_audience": config.oidc_api_audience,
            "offline_static_mode": False,
        },
    )
    plan = root / "environment.tfplan"
    return environment_root, backend, tfvars, plan


def terraform_init(
    config: LifecycleConfig,
    state: LifecycleState,
    config_path: Path,
    session: AwsCli,
) -> tuple[Path, Path, Path]:
    terraform = require_command("terraform")
    environment_root, backend, tfvars, plan = terraform_files(
        config, state, config_path
    )
    run_process(
        [
            terraform,
            f"-chdir={environment_root}",
            "init",
            "-reconfigure",
            f"-backend-config={backend}",
        ],
        env=terraform_environment(config, session),
        timeout=600,
        label="Terraform remote-backend initialization",
        safe_failure_prefix="Error:",
    )
    return environment_root, tfvars, plan


def create_plan(
    config: LifecycleConfig,
    state: LifecycleState,
    config_path: Path,
    session: AwsCli,
) -> dict[str, object]:
    terraform = require_command("terraform")
    environment_root, tfvars, plan = terraform_init(config, state, config_path, session)
    run_process(
        [
            terraform,
            f"-chdir={environment_root}",
            "plan",
            "-input=false",
            "-refresh=true",
            f"-var-file={tfvars}",
            f"-out={plan}",
        ],
        env=terraform_environment(config, session),
        timeout=1200,
        label="Terraform fresh plan",
        safe_failure_prefix="Error:",
    )
    shown = run_process(
        [terraform, f"-chdir={environment_root}", "show", "-json", str(plan)],
        env=terraform_environment(config, session),
        timeout=300,
        label="Terraform plan inspection",
        safe_failure_prefix="Error:",
    )
    try:
        payload = json.loads(shown.stdout)
    except json.JSONDecodeError as error:
        raise LifecycleError("Terraform plan JSON was invalid.") from error
    counts = {"create": 0, "update": 0, "delete": 0, "no-op": 0}
    for change in payload.get("resource_changes", []):
        actions = change.get("change", {}).get("actions", [])
        if actions == ["create"]:
            counts["create"] += 1
        elif actions == ["update"]:
            counts["update"] += 1
        elif actions == ["delete"]:
            counts["delete"] += 1
        elif actions == ["no-op"]:
            counts["no-op"] += 1
        else:
            raise LifecycleError(
                "Terraform plan contains a replacement or unknown action."
            )
    if counts["update"] or counts["delete"] or counts["create"] == 0:
        raise LifecycleError(
            "Construction plan is not a fresh create-only environment."
        )
    return {
        "sha256": sha256_file(plan),
        "createdAt": isoformat(utc_now()),
        "counts": counts,
        "fresh": True,
    }


def terraform_output(
    config: LifecycleConfig,
    state: LifecycleState,
    config_path: Path,
    session: AwsCli,
) -> dict[str, Any]:
    terraform = require_command("terraform")
    environment_root, _, _ = terraform_init(config, state, config_path, session)
    result = run_process(
        [terraform, f"-chdir={environment_root}", "output", "-json"],
        env=terraform_environment(config, session),
        timeout=300,
        label="Terraform output read",
        safe_failure_prefix="Error:",
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise LifecycleError("Terraform outputs were invalid.") from error
    if not isinstance(payload, dict):
        raise LifecycleError("Terraform outputs were not an object.")
    return payload


def output_value(outputs: Mapping[str, Any], name: str) -> Any:
    entry = outputs.get(name)
    if not isinstance(entry, dict) or "value" not in entry:
        raise LifecycleError(f"Terraform output is missing: {name}.")
    return entry["value"]


def wait_for_build(
    client: AwsCli, build_id: str, *, timeout: int = BUILD_TIMEOUT_SECONDS
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.call("codebuild", "batch-get-builds", "--ids", build_id) or {}
        builds = response.get("builds")
        if not isinstance(builds, list) or len(builds) != 1:
            raise LifecycleError("CodeBuild response omitted the exact build.")
        status = builds[0].get("buildStatus")
        if status == "SUCCEEDED":
            return dict(builds[0])
        if status in {"FAILED", "FAULT", "STOPPED", "TIMED_OUT"}:
            raise LifecycleError(
                "CodeBuild execution failed; private logs were retained in AWS."
            )
        time.sleep(10)
    raise LifecycleError("CodeBuild execution exceeded the accepted timeout.")


def run_preflight(
    config: LifecycleConfig,
    config_path: Path,
    source: AwsCli,
    *,
    require_remote: bool = True,
    recover_exact_lease: bool = False,
) -> tuple[AwsCli, dict[str, object]]:
    verify_local_source(config, require_remote=require_remote)
    require_command("git")
    require_command("terraform")
    if not sys.version.startswith("3.13"):
        raise LifecycleError("Python 3.13 is required by the repository contract.")
    verify_source(config, source)
    operator = assume_role(
        source,
        config,
        "operator_deployment",
        "portfolio-lifecycle-preflight",
    )
    static = verify_static_iam(config, source.executable)
    controller = verify_controller(config, operator, reconcile_image_buildspec=True)
    verify_image_repositories(config, operator)
    verify_state_bucket(config, operator)
    lease_state = "absent"
    for key in (config.configuration_key, config.secret_key):
        response = operator.call(
            "s3api",
            "head-object",
            "--bucket",
            config.state_bucket,
            "--key",
            key,
            allow_error_codes=("404", "Not Found", "NoSuchKey"),
        )
        if response is not None:
            raise LifecycleError(
                "An existing lifecycle control object blocks construction."
            )
    lease = s3_get_json(
        operator,
        config,
        config.lease_key,
        runtime_directory(config_path) / "preflight-lease.json",
        allow_missing=True,
    )
    if lease is not None:
        if not recover_exact_lease:
            raise LifecycleError("An existing lifecycle lease blocks construction.")
        validate_lease_payload(lease[0], config)
        lease_state = "recovered-exact"
    inventory_probe = assume_role(
        operator,
        config,
        "destroy",
        "portfolio-preflight-inventory",
    )
    namespaces = inventory_probe.call("servicediscovery", "list-namespaces") or {}
    services = inventory_probe.call("servicediscovery", "list-services") or {}
    if namespaces.get("Namespaces") or services.get("Services"):
        raise LifecycleError("Cloud Map is not empty; owner review is required.")
    operator.effects.add(inventory_probe.effects)
    proof = {
        "sourceIdentity": "verified",
        "operatorSession": "verified",
        "staticIam": "verified",
        "persistentController": "verified",
        "imageBuildspecReconciled": controller["imageBuildspecReconciled"],
        "persistentImageRepositories": 3,
        "persistentStateBucket": "verified",
        "sourceRevision": config.source_sha,
        "region": config.region,
        "cloudMapIsolation": "empty",
        "cloudMapInventorySession": "destroy-read-only",
        "remoteControlObjects": 1 if lease_state == "recovered-exact" else 0,
        "lifecycleLease": lease_state,
        "readOnly": not bool(controller["imageBuildspecReconciled"]),
        "staticIamReadCalls": int(static.get("attestationAwsReadCalls", 0)),
        **{
            key: value
            for key, value in controller.items()
            if key.endswith("BuildspecSha256")
        },
    }
    assert_public_safe(proof)
    write_private_json(runtime_directory(config_path) / "preflight.json", proof)
    return operator, proof


def run_resume_preflight(
    config: LifecycleConfig, config_path: Path, source: AwsCli
) -> AwsCli:
    verify_local_source(config, require_remote=True)
    require_command("git")
    require_command("terraform")
    if not sys.version.startswith("3.13"):
        raise LifecycleError("Python 3.13 is required by the repository contract.")
    verify_source(config, source)
    operator = assume_role(
        source,
        config,
        "operator_deployment",
        "portfolio-lifecycle-resume",
    )
    verify_static_iam(config, source.executable)
    verify_controller(config, operator, reconcile_image_buildspec=True)
    verify_image_repositories(config, operator)
    verify_state_bucket(config, operator)
    return operator


def command_configure(args: argparse.Namespace, source: AwsCli) -> dict[str, object]:
    config = derive_config(args, source)
    verify_local_source(config, require_remote=False)
    write_private_json(args.config, config.to_dict())
    result = {
        "configured": True,
        "sourceRevision": config.source_sha,
        "environment": config.environment,
        "region": config.region,
        "configurationSource": "repository-and-sanitized-aws-identity",
        "callerMode": config.caller_mode,
        "callerEvent": config.caller_event or "none",
        **source.effects.result(),
    }
    assert_public_safe(result)
    return result


def command_preflight(
    config: LifecycleConfig, config_path: Path, source: AwsCli
) -> dict[str, object]:
    operator, proof = run_preflight(config, config_path, source)
    effects = Effects()
    effects.add(source.effects)
    effects.add(operator.effects)
    return {**proof, **effects.result()}


def read_exact_image_digests(client: AwsCli, config: LifecycleConfig) -> dict[str, str]:
    images: dict[str, str] = {}
    for purpose in ("web", "api", "ml"):
        response = client.call(
            "ecr",
            "describe-images",
            "--repository-name",
            f"{config.name_prefix}/{purpose}",
            "--image-ids",
            f"imageTag={config.image_tag}",
            allow_error_codes=("ImageNotFoundException",),
        )
        if response is None:
            continue
        details = response.get("imageDetails", [])
        if not isinstance(details, list) or len(details) != 1:
            raise LifecycleError("Exact immutable image inventory was ambiguous.")
        detail = details[0]
        tags = detail.get("imageTags", []) if isinstance(detail, dict) else []
        if not isinstance(tags, list) or config.image_tag not in tags:
            raise LifecycleError("Immutable image tag did not bind the exact source.")
        digest = str(detail.get("imageDigest", ""))
        if DIGEST_PATTERN.fullmatch(digest) is None:
            raise LifecycleError("Exact immutable image digest was malformed.")
        images[purpose] = digest
    return images


def command_publish_images(
    config: LifecycleConfig, config_path: Path, source: AwsCli
) -> dict[str, object]:
    runtime = runtime_directory(config_path)
    verify_source(config, source)
    probe = assume_role(
        source, config, "operator_deployment", "portfolio-publish-probe"
    )
    remote = read_remote_state(probe, config, config_path, allow_missing=True)
    if remote is None:
        operator, proof = run_preflight(
            config,
            config_path,
            source,
            recover_exact_lease=True,
        )
        state = LifecycleState(config.source_sha, sha256_json(config.to_dict()))
        state.transition(Phase.PREFLIGHTED, checkpoint={"preflight": "passed"})
        if proof["lifecycleLease"] == "absent":
            s3_put_json(
                operator,
                config,
                config.lease_key,
                {
                    "schemaVersion": 1,
                    "deploymentId": config.source_sha,
                    "acquiredAt": isoformat(utc_now()),
                },
                runtime / "lease-upload.json",
                if_none_match=True,
                resource_delta=1,
            )
        etag = write_remote_state(
            operator, config, config_path, state, if_none_match=True
        )
    else:
        operator = run_resume_preflight(config, config_path, source)
        state, etag = remote
        if state.phase == Phase.FAILED and state.last_failure is not None:
            if state.last_failure.get("operation") != "publish-images":
                raise LifecycleError("A later failed operation owns this lifecycle.")
            state.resume(Phase.PREFLIGHTED)
        elif state.phase != Phase.PREFLIGHTED:
            raise LifecycleError(
                "Image publication is already complete or cannot resume."
            )
    publication = "built"
    try:
        existing_images = read_exact_image_digests(operator, config)
        if existing_images and set(existing_images) != {"web", "api", "ml"}:
            raise LifecycleError(
                "Immutable image publication is partial; destroy is required before retry."
            )
        if existing_images:
            images = existing_images
            publication = "reused"
        else:
            response = (
                operator.call(
                    "codebuild",
                    "start-build",
                    "--project-name",
                    config.projects["image"],
                )
                or {}
            )
            build_id = str(response.get("build", {}).get("id", ""))
            if not build_id:
                raise LifecycleError(
                    "Image build did not return an exact build identity."
                )
            completed_build = wait_for_build(operator, build_id)
            exported = {
                str(item.get("name")): str(item.get("value"))
                for item in completed_build.get("exportedEnvironmentVariables", [])
                if isinstance(item, dict)
            }
            images = {
                purpose: exported.get(f"{purpose.upper()}_DIGEST", "")
                for purpose in ("web", "api", "ml")
            }
            published_images = read_exact_image_digests(operator, config)
            if published_images != images:
                raise LifecycleError(
                    "CodeBuild digest evidence did not match immutable ECR read-back."
                )
        state.set_images(images)
    except LifecycleError:
        state.record_failure("publish-images")
        write_remote_state(operator, config, config_path, state, if_match=etag)
        raise
    state.transition(
        Phase.IMAGES_PUBLISHED,
        checkpoint={
            "imageBuild": "passed" if publication == "built" else "reused-exact"
        },
    )
    write_remote_state(operator, config, config_path, state, if_match=etag)
    effects = Effects()
    effects.add(source.effects)
    effects.add(probe.effects)
    effects.add(operator.effects)
    result = {
        "phase": state.phase.value,
        "sourceRevision": config.source_sha,
        "immutableImages": len(state.images),
        "imagePublication": publication,
        "lease": "acquired",
        **effects.result(),
    }
    assert_public_safe(result)
    return result


def schedule_expression(expiry: datetime) -> str:
    return f"at({expiry.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%S')})"


def schedule_target(config: LifecycleConfig) -> str:
    return canonical_json(
        {
            "Arn": project_arn(config, "destroy"),
            "RoleArn": role_arn(config, "scheduler"),
            "RetryPolicy": {
                "MaximumEventAgeInSeconds": 3600,
                "MaximumRetryAttempts": 3,
            },
        }
    )


def read_schedule(client: AwsCli, config: LifecycleConfig) -> dict[str, Any] | None:
    response = client.call(
        "scheduler",
        "get-schedule",
        "--name",
        config.schedule_name,
        "--group-name",
        config.schedule_group_name,
        allow_error_codes=("ResourceNotFoundException",),
    )
    if response is None:
        return None
    if not isinstance(response, dict):
        raise LifecycleError("Fallback schedule read-back was malformed.")
    return response


def verify_schedule_payload(
    schedule: Mapping[str, Any], config: LifecycleConfig, expected_expiry: datetime
) -> None:
    expected_target = json.loads(schedule_target(config))
    if (
        schedule.get("Name") != config.schedule_name
        or schedule.get("GroupName") != config.schedule_group_name
        or schedule.get("State") != "ENABLED"
        or schedule.get("ScheduleExpression") != schedule_expression(expected_expiry)
        or schedule.get("ScheduleExpressionTimezone") != "UTC"
        or schedule.get("FlexibleTimeWindow") != {"Mode": "OFF"}
        or schedule.get("ActionAfterCompletion") != "NONE"
        or schedule.get("Target") != expected_target
        or any(key in schedule for key in ("StartDate", "EndDate", "KmsKeyArn"))
    ):
        raise LifecycleError("Fallback schedule read-back drifted.")


def verify_schedule(
    client: AwsCli, config: LifecycleConfig, expected_expiry: datetime
) -> None:
    schedule = read_schedule(client, config)
    if schedule is None:
        raise LifecycleError("Fallback schedule is missing.")
    verify_schedule_payload(schedule, config, expected_expiry)


def ensure_schedule(
    client: AwsCli, config: LifecycleConfig, expected_expiry: datetime
) -> str:
    existing = read_schedule(client, config)
    if existing is not None:
        verify_schedule_payload(existing, config, expected_expiry)
        if expected_expiry <= utc_now():
            raise LifecycleError("Existing fallback schedule is expired.")
        return "reused"
    client.call(
        "scheduler",
        "create-schedule",
        "--name",
        config.schedule_name,
        "--group-name",
        config.schedule_group_name,
        "--schedule-expression",
        schedule_expression(expected_expiry),
        "--schedule-expression-timezone",
        "UTC",
        "--flexible-time-window",
        '{"Mode":"OFF"}',
        "--action-after-completion",
        "NONE",
        "--target",
        schedule_target(config),
        "--client-token",
        config.source_sha[:32],
        resource_delta=1,
    )
    verify_schedule(client, config, expected_expiry)
    return "created"


def schedule_matches_payload(
    schedule: Mapping[str, Any], config: LifecycleConfig, expected_expiry: datetime
) -> bool:
    try:
        verify_schedule_payload(schedule, config, expected_expiry)
    except LifecycleError:
        return False
    return True


def update_schedule(
    client: AwsCli, config: LifecycleConfig, expected_expiry: datetime
) -> None:
    client.call(
        "scheduler",
        "update-schedule",
        "--name",
        config.schedule_name,
        "--group-name",
        config.schedule_group_name,
        "--schedule-expression",
        schedule_expression(expected_expiry),
        "--schedule-expression-timezone",
        "UTC",
        "--flexible-time-window",
        '{"Mode":"OFF"}',
        "--action-after-completion",
        "NONE",
        "--state",
        "ENABLED",
        "--target",
        schedule_target(config),
    )


def reconcile_schedule_extension(
    client: AwsCli,
    config: LifecycleConfig,
    current_expiry: datetime,
    new_expiry: datetime,
    *,
    now: datetime,
) -> str:
    existing = read_schedule(client, config)
    if existing is None:
        raise LifecycleError("Fallback schedule is missing.")
    if schedule_matches_payload(existing, config, new_expiry):
        if new_expiry <= now:
            raise LifecycleError("Extended fallback schedule is expired.")
        return "reused"
    verify_schedule_payload(existing, config, current_expiry)
    if current_expiry <= now:
        raise LifecycleError("An expired fallback cannot be extended.")
    update_schedule(client, config, new_expiry)
    verify_schedule(client, config, new_expiry)
    return "updated"


def schedule_window(schedule: Mapping[str, Any]) -> tuple[datetime, datetime]:
    expression = str(schedule.get("ScheduleExpression", ""))
    if not expression.startswith("at(") or not expression.endswith(")"):
        raise LifecycleError("Fallback schedule expression was malformed.")
    try:
        expiry = datetime.strptime(expression[3:-1], "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=UTC
        )
    except ValueError as error:
        raise LifecycleError("Fallback schedule expression was malformed.") from error
    registered = parse_time(str(schedule.get("CreationDate", "")))
    validate_fallback_window(registered, expiry)
    return registered, expiry


def fallback_intent(
    state: LifecycleState, config: LifecycleConfig
) -> tuple[datetime, datetime] | None:
    candidate = state.checkpoints.get("fallbackIntent")
    if candidate is None:
        return None
    if not isinstance(candidate, dict) or set(candidate) != {
        "scheduleName",
        "registeredAt",
        "expiresAt",
    }:
        raise LifecycleError("Fallback registration intent is malformed.")
    if candidate.get("scheduleName") != config.schedule_name:
        raise LifecycleError("Fallback registration intent is foreign.")
    registered = parse_time(str(candidate.get("registeredAt", "")))
    expiry = parse_time(str(candidate.get("expiresAt", "")))
    validate_fallback_window(registered, expiry)
    return registered, expiry


def fallback_extend_intent(
    state: LifecycleState, config: LifecycleConfig, minutes: int
) -> tuple[datetime, datetime] | None:
    candidate = state.checkpoints.get("fallbackExtendIntent")
    if candidate is None:
        return None
    if not isinstance(candidate, dict) or set(candidate) != {
        "scheduleName",
        "currentExpiresAt",
        "newExpiresAt",
        "addedMinutes",
    }:
        raise LifecycleError("Fallback extension intent is malformed.")
    added_minutes = candidate.get("addedMinutes")
    if type(added_minutes) is not int or added_minutes <= 0:
        raise LifecycleError("Fallback extension intent duration is malformed.")
    if added_minutes != minutes:
        raise LifecycleError("Fallback extension retry changed its duration.")
    if candidate.get("scheduleName") != config.schedule_name:
        raise LifecycleError("Fallback extension intent is foreign.")
    current = parse_time(str(candidate.get("currentExpiresAt", "")))
    new_expiry = parse_time(str(candidate.get("newExpiresAt", "")))
    state_current = parse_time(str(state.fallback.get("expiresAt", "")))
    registered = parse_time(str(state.fallback.get("registeredAt", "")))
    if current != state_current or new_expiry != current + timedelta(minutes=minutes):
        raise LifecycleError("Fallback extension intent drifted.")
    validate_fallback_window(registered, new_expiry)
    return current, new_expiry


def command_register_fallback(
    config: LifecycleConfig,
    config_path: Path,
    source: AwsCli,
    ttl_minutes: int,
) -> dict[str, object]:
    verify_source(config, source)
    operator = assume_role(
        source, config, "operator_deployment", "portfolio-register-fallback"
    )
    verify_controller(config, operator, reconcile_image_buildspec=False)
    remote = read_remote_state(operator, config, config_path)
    if remote is None:
        raise LifecycleError("Remote lifecycle is missing.")
    state, etag = remote
    if state.phase != Phase.IMAGES_PUBLISHED:
        raise LifecycleError("Fallback registration requires published images.")
    intent = fallback_intent(state, config)
    plan_path = runtime_directory(config_path) / "environment.tfplan"
    if intent is None:
        existing = read_schedule(operator, config)
        if existing is None:
            registered = utc_now()
            expiry = registered + timedelta(minutes=ttl_minutes)
            validate_fallback_window(registered, expiry)
        else:
            registered, expiry = schedule_window(existing)
            verify_schedule_payload(existing, config, expiry)
            if expiry <= utc_now():
                raise LifecycleError("Existing fallback schedule is expired.")
        state.plan = create_plan(config, state, config_path, operator)
        state.transition(
            Phase.IMAGES_PUBLISHED,
            checkpoint={
                "fallbackIntent": {
                    "scheduleName": config.schedule_name,
                    "registeredAt": isoformat(registered),
                    "expiresAt": isoformat(expiry),
                }
            },
        )
        etag = write_remote_state(operator, config, config_path, state, if_match=etag)
    else:
        registered, expiry = intent
        if expiry <= utc_now():
            raise LifecycleError("Fallback registration intent is expired.")
        if not plan_is_fresh(state, plan_path):
            state.plan = create_plan(config, state, config_path, operator)
            state.transition(Phase.IMAGES_PUBLISHED)
            etag = write_remote_state(
                operator, config, config_path, state, if_match=etag
            )
    registration = ensure_schedule(operator, config, expiry)
    state.set_fallback(
        schedule_name=config.schedule_name,
        registered_at=registered,
        expires_at=expiry,
    )
    del state.checkpoints["fallbackIntent"]
    state.transition(
        Phase.FALLBACK_REGISTERED,
        checkpoint={
            "fallback": "verified",
            "fallbackRegistration": registration,
            "plan": "fresh",
        },
    )
    write_remote_state(operator, config, config_path, state, if_match=etag)
    effects = Effects()
    effects.add(source.effects)
    effects.add(operator.effects)
    result = {
        "phase": state.phase.value,
        "fallback": "verified",
        "fallbackRegistration": registration,
        "ttlMinutes": int((expiry - registered).total_seconds() // 60),
        "plan": state.plan.get("counts", {}),
        **effects.result(),
    }
    assert_public_safe(result)
    return result


def plan_is_fresh(state: LifecycleState, plan_path: Path) -> bool:
    if not plan_path.is_file() or state.plan.get("fresh") is not True:
        return False
    if state.plan.get("sha256") != sha256_file(plan_path):
        return False
    created = parse_time(str(state.plan.get("createdAt", "")))
    return (utc_now() - created).total_seconds() <= PLAN_MAX_AGE_SECONDS


def command_apply(
    config: LifecycleConfig, config_path: Path, source: AwsCli
) -> dict[str, object]:
    verify_source(config, source)
    operator = assume_role(source, config, "operator_deployment", "portfolio-apply")
    remote = read_remote_state(operator, config, config_path)
    if remote is None:
        raise LifecycleError("Remote lifecycle is missing.")
    state, etag = remote
    if state.phase != Phase.FALLBACK_REGISTERED:
        raise LifecycleError("Apply requires a verified fallback.")
    expiry = parse_time(str(state.fallback.get("expiresAt", "")))
    verify_schedule(operator, config, expiry)
    if expiry <= utc_now() + timedelta(minutes=20):
        raise LifecycleError("Too little verified fallback time remains for apply.")
    _, _, _, plan = terraform_files(config, state, config_path)
    if not plan_is_fresh(state, plan):
        state.plan = create_plan(config, state, config_path, operator)
    state.transition(Phase.APPLYING, checkpoint={"apply": "running"})
    etag = write_remote_state(operator, config, config_path, state, if_match=etag)
    terraform = require_command("terraform")
    environment_root, _, _ = terraform_init(config, state, config_path, operator)
    try:
        run_process(
            [
                terraform,
                f"-chdir={environment_root}",
                "apply",
                "-input=false",
                "-auto-approve",
                str(plan),
            ],
            env=terraform_environment(config, operator),
            timeout=3600,
            label="Terraform managed environment apply",
            safe_failure_prefix="Error:",
        )
    except LifecycleError:
        state.record_failure("apply")
        state.checkpoints["apply"] = "failed"
        write_remote_state(operator, config, config_path, state, if_match=etag)
        raise
    state.transition(Phase.APPLIED, checkpoint={"apply": "passed"})
    write_remote_state(operator, config, config_path, state, if_match=etag)
    effects = Effects()
    effects.add(source.effects)
    effects.add(operator.effects)
    result = {
        "phase": state.phase.value,
        "terraform": "applied",
        "fallback": "retained",
        **effects.result(),
    }
    assert_public_safe(result)
    return result


def migration_attempt(state: LifecycleState) -> int:
    candidate = state.checkpoints.get("migrationAttempt", 0)
    if type(candidate) is not int or candidate < 0:
        raise LifecycleError("Migration attempt checkpoint is malformed.")
    return candidate


def expected_migration_intent(
    state: LifecycleState,
    services: Mapping[str, Any],
    network_configuration: str,
    tags: Sequence[Mapping[str, str]],
    *,
    attempt: int,
    requested_at: datetime,
) -> dict[str, object]:
    cluster = str(services["ecs_cluster"])
    task_definition = str(services["migration_task_definition"])
    request_digest = sha256_json(
        {
            "cluster": cluster,
            "taskDefinition": task_definition,
            "launchType": "FARGATE",
            "platformVersion": "1.4.0",
            "networkConfiguration": json.loads(network_configuration),
            "tags": list(tags),
            "propagateTags": "TASK_DEFINITION",
        }
    )
    client_token = sha256_json(
        {
            "operation": "migrate",
            "deploymentId": state.deployment_id,
            "createdAt": state.created_at,
            "attempt": attempt,
            "requestDigest": request_digest,
        }
    )
    return {
        "attempt": attempt,
        "requestedAt": isoformat(requested_at),
        "cluster": cluster,
        "taskDefinition": task_definition,
        "requestDigest": request_digest,
        "clientToken": client_token,
        "startedBy": f"portfolio-{client_token[:26]}",
    }


def read_migration_intent(
    state: LifecycleState,
    services: Mapping[str, Any],
    network_configuration: str,
    tags: Sequence[Mapping[str, str]],
) -> dict[str, object] | None:
    candidate = state.checkpoints.get("migrationIntent")
    if candidate is None:
        return None
    expected_keys = {
        "attempt",
        "requestedAt",
        "cluster",
        "taskDefinition",
        "requestDigest",
        "clientToken",
        "startedBy",
    }
    if not isinstance(candidate, dict) or set(candidate) != expected_keys:
        raise LifecycleError("Migration intent is malformed.")
    attempt = candidate.get("attempt")
    if type(attempt) is not int or attempt != migration_attempt(state) + 1:
        raise LifecycleError("Migration intent attempt drifted.")
    requested_at = parse_time(str(candidate.get("requestedAt", "")))
    expected = expected_migration_intent(
        state,
        services,
        network_configuration,
        tags,
        attempt=attempt,
        requested_at=requested_at,
    )
    if candidate != expected:
        raise LifecycleError("Migration intent is foreign or drifted.")
    return expected


def validate_migration_task_arn(
    task_arn: str, config: LifecycleConfig, cluster: str
) -> None:
    prefix = (
        f"arn:{config.partition}:ecs:{config.region}:{config.account_id}:"
        f"task/{cluster}/"
    )
    task_id = task_arn.removeprefix(prefix)
    if (
        not task_arn.startswith(prefix)
        or not task_id
        or len(task_id) > 64
        or any(not (character.isalnum() or character == "-") for character in task_id)
    ):
        raise LifecycleError("Migration task identity is foreign or malformed.")


def verify_migration_task(
    task: Mapping[str, Any],
    config: LifecycleConfig,
    intent: Mapping[str, object],
    task_arn: str,
) -> int:
    cluster = str(intent["cluster"])
    cluster_arn = (
        f"arn:{config.partition}:ecs:{config.region}:{config.account_id}:"
        f"cluster/{cluster}"
    )
    raw_tags = task.get("tags")
    if not isinstance(raw_tags, list):
        raise LifecycleError("Migration task tags are missing.")
    tags = {
        str(item.get("key")): str(item.get("value"))
        for item in raw_tags
        if isinstance(item, dict)
    }
    containers = task.get("containers")
    if (
        task.get("taskArn") != task_arn
        or task.get("clusterArn") != cluster_arn
        or task.get("taskDefinitionArn") != intent["taskDefinition"]
        or task.get("startedBy") != intent["startedBy"]
        or task.get("launchType") != "FARGATE"
        or task.get("platformVersion") != "1.4.0"
        or task.get("lastStatus") != "STOPPED"
        or task.get("desiredStatus") != "STOPPED"
        or any(tags.get(key) != value for key, value in config.ownership_tags.items())
        or not isinstance(containers, list)
        or len(containers) != 1
        or not isinstance(containers[0], dict)
        or type(containers[0].get("exitCode")) is not int
    ):
        raise LifecycleError("Migration task read-back drifted.")
    return int(containers[0]["exitCode"])


def command_migrate(
    config: LifecycleConfig, config_path: Path, source: AwsCli
) -> dict[str, object]:
    verify_source(config, source)
    operator = assume_role(source, config, "operator_deployment", "portfolio-migrate")
    remote = read_remote_state(operator, config, config_path)
    if remote is None:
        raise LifecycleError("Remote lifecycle is missing.")
    state, etag = remote
    if state.phase == Phase.FAILED and state.last_failure is not None:
        if state.last_failure.get("operation") != "migrate":
            raise LifecycleError("A different failed operation owns this lifecycle.")
        state.resume(Phase.APPLIED)
    if state.phase != Phase.APPLIED:
        raise LifecycleError("Migration requires a completed apply.")
    outputs = terraform_output(config, state, config_path, operator)
    services = output_value(outputs, "service_identifiers")
    network = output_value(outputs, "migration_network")
    if not isinstance(services, dict) or not isinstance(network, dict):
        raise LifecycleError("Migration outputs are incomplete.")
    network_configuration = canonical_json(
        {
            "awsvpcConfiguration": {
                "subnets": network["subnet_ids"],
                "securityGroups": [network["security_group_id"]],
                "assignPublicIp": "ENABLED",
            }
        }
    )
    tags = [
        {"key": key, "value": value} for key, value in config.ownership_tags.items()
    ]
    intent = read_migration_intent(state, services, network_configuration, tags)
    intent_was_present = intent is not None
    if intent is None:
        requested_at = utc_now()
        intent = expected_migration_intent(
            state,
            services,
            network_configuration,
            tags,
            attempt=migration_attempt(state) + 1,
            requested_at=requested_at,
        )
        state.transition(
            Phase.APPLIED,
            checkpoint={"migration": "running", "migrationIntent": intent},
        )
        etag = write_remote_state(operator, config, config_path, state, if_match=etag)
    task_arn_checkpoint = state.checkpoints.get("migrationTaskArn")
    if task_arn_checkpoint is None:
        requested_at = parse_time(str(intent["requestedAt"]))
        if intent_was_present and utc_now() >= requested_at + timedelta(minutes=50):
            raise LifecycleError(
                "Unreconciled migration intent exceeded the safe ECS idempotency window."
            )
        response = (
            operator.call(
                "ecs",
                "run-task",
                "--cluster",
                str(intent["cluster"]),
                "--task-definition",
                str(intent["taskDefinition"]),
                "--launch-type",
                "FARGATE",
                "--platform-version",
                "1.4.0",
                "--network-configuration",
                network_configuration,
                "--started-by",
                str(intent["startedBy"]),
                "--client-token",
                str(intent["clientToken"]),
                "--tags",
                canonical_json(tags),
                "--propagate-tags",
                "TASK_DEFINITION",
                resource_delta=1,
            )
            or {}
        )
        tasks = response.get("tasks")
        failures = response.get("failures", [])
        if (
            not isinstance(tasks, list)
            or len(tasks) != 1
            or not isinstance(failures, list)
            or failures
        ):
            raise LifecycleError("Migration did not start one exact ECS task.")
        task_arn = str(tasks[0].get("taskArn", ""))
        validate_migration_task_arn(task_arn, config, str(intent["cluster"]))
        state.transition(
            Phase.APPLIED,
            checkpoint={"migration": "running", "migrationTaskArn": task_arn},
        )
        etag = write_remote_state(operator, config, config_path, state, if_match=etag)
    else:
        if not isinstance(task_arn_checkpoint, str):
            raise LifecycleError("Migration task checkpoint is malformed.")
        task_arn = task_arn_checkpoint
        validate_migration_task_arn(task_arn, config, str(intent["cluster"]))
    try:
        operator.wait(
            "ecs",
            "tasks-stopped",
            "--cluster",
            str(intent["cluster"]),
            "--tasks",
            task_arn,
        )
        described = (
            operator.call(
                "ecs",
                "describe-tasks",
                "--cluster",
                str(intent["cluster"]),
                "--tasks",
                task_arn,
                "--include",
                "TAGS",
            )
            or {}
        )
        stopped = described.get("tasks")
        failures = described.get("failures", [])
        if (
            not isinstance(stopped, list)
            or len(stopped) != 1
            or not isinstance(stopped[0], dict)
            or not isinstance(failures, list)
            or failures
        ):
            raise LifecycleError("Migration task read-back was incomplete.")
        exit_code = verify_migration_task(stopped[0], config, intent, task_arn)
    except LifecycleError as observation_error:
        state.record_failure("migrate")
        state.checkpoints["migration"] = "unknown"
        try:
            write_remote_state(operator, config, config_path, state, if_match=etag)
        except LifecycleError as checkpoint_error:
            observation_error.add_note(
                "The migration observation failure checkpoint also failed safely."
            )
            raise observation_error from checkpoint_error
        raise
    if exit_code != 0:
        state.checkpoints["migrationAttempt"] = intent["attempt"]
        state.checkpoints.pop("migrationIntent", None)
        state.checkpoints.pop("migrationTaskArn", None)
        state.record_failure("migrate")
        state.checkpoints["migration"] = "failed"
        write_remote_state(operator, config, config_path, state, if_match=etag)
        raise LifecycleError("Migration task did not exit successfully.")
    state.checkpoints["migrationAttempt"] = intent["attempt"]
    state.checkpoints.pop("migrationIntent", None)
    state.checkpoints.pop("migrationTaskArn", None)
    state.transition(Phase.MIGRATED, checkpoint={"migration": "passed"})
    write_remote_state(operator, config, config_path, state, if_match=etag)
    effects = Effects()
    effects.add(source.effects)
    effects.add(operator.effects)
    result = {"phase": state.phase.value, "migration": "passed", **effects.result()}
    assert_public_safe(result)
    return result


def seed_recovery_path(config_path: Path) -> Path:
    return runtime_directory(config_path) / "seed-operation.json"


def validate_seed_owner(value: object) -> str:
    owner = str(value)
    if len(owner) != SEED_OWNER_LENGTH or any(
        character not in string.hexdigits.lower() for character in owner
    ):
        raise LifecycleError("Seed operation owner is malformed.")
    return owner


def validate_seed_intent(
    candidate: object, state: LifecycleState, username: str
) -> dict[str, str]:
    if not isinstance(candidate, dict) or set(candidate) != {
        "owner",
        "requestedAt",
        "username",
    }:
        raise LifecycleError("Seed intent is malformed.")
    owner = validate_seed_owner(candidate.get("owner"))
    requested_at = str(candidate.get("requestedAt", ""))
    parse_time(requested_at)
    if candidate.get("username") != username:
        raise LifecycleError("Seed intent is foreign or drifted.")
    return {"owner": owner, "requestedAt": requested_at, "username": username}


def load_seed_recovery(
    state: LifecycleState,
    config_path: Path,
    username: str,
    intent: dict[str, str] | None,
) -> dict[str, str]:
    path = seed_recovery_path(config_path)
    record: dict[str, Any] | None = None
    if path.exists():
        loaded = load_json(path)
        if not isinstance(loaded, dict):
            raise LifecycleError("Local seed recovery identity is malformed.")
        record = loaded
    expected_keys = {
        "schemaVersion",
        "deploymentId",
        "lifecycleCreatedAt",
        "owner",
        "requestedAt",
        "username",
    }
    current_record = (
        record is not None
        and set(record) == expected_keys
        and record.get("schemaVersion") == 1
        and record.get("deploymentId") == state.deployment_id
        and record.get("lifecycleCreatedAt") == state.created_at
        and record.get("username") == username
    )
    if current_record:
        owner = validate_seed_owner(record.get("owner"))
        requested_at = str(record.get("requestedAt", ""))
        parse_time(requested_at)
        recovery = {
            "owner": owner,
            "requestedAt": requested_at,
            "username": username,
        }
    elif intent is not None:
        raise LifecycleError(
            "Seed operation is owned by another invocation; exact local recovery "
            "identity is unavailable."
        )
    else:
        recovery = {
            "owner": secrets.token_hex(SEED_OWNER_LENGTH // 2),
            "requestedAt": isoformat(utc_now()),
            "username": username,
        }
        write_private_json(
            path,
            {
                "schemaVersion": 1,
                "deploymentId": state.deployment_id,
                "lifecycleCreatedAt": state.created_at,
                **recovery,
            },
        )
    if intent is not None and recovery != intent:
        raise LifecycleError(
            "Seed operation is owned by another invocation; recovery was rejected."
        )
    return recovery


def generated_password() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#%+-_"
    while True:
        value = "".join(secrets.choice(alphabet) for _ in range(32))
        if (
            any(character.islower() for character in value)
            and any(character.isupper() for character in value)
            and any(character.isdigit() for character in value)
            and any(character in "!@#%+-_" for character in value)
        ):
            return value


def command_seed(
    config: LifecycleConfig, config_path: Path, source: AwsCli
) -> dict[str, object]:
    with seed_operation_lock(config_path):
        verify_source(config, source)
        operator = assume_role(source, config, "operator_deployment", "portfolio-seed")
        remote = read_remote_state(operator, config, config_path)
        if remote is None:
            raise LifecycleError("Remote lifecycle is missing.")
        state, etag = remote
        username = "reviewer@synthetic.invalid"
        raw_intent = state.checkpoints.get("seedIntent")
        intent = (
            None
            if raw_intent is None
            else validate_seed_intent(raw_intent, state, username)
        )
        if state.phase == Phase.FAILED and state.last_failure is not None:
            if state.last_failure.get("operation") != "seed":
                raise LifecycleError(
                    "A different failed operation owns this lifecycle."
                )
            if intent is None:
                raise LifecycleError("Failed seed has no exact recovery owner.")
            recovery = load_seed_recovery(state, config_path, username, intent)
            state.resume(Phase.MIGRATED)
            state.transition(
                Phase.MIGRATED,
                checkpoint={"seed": "running", "seedIntent": recovery},
            )
            etag = write_remote_state(
                operator, config, config_path, state, if_match=etag
            )
        elif state.phase == Phase.MIGRATED:
            recovery = load_seed_recovery(state, config_path, username, intent)
            if intent is None:
                state.transition(
                    Phase.MIGRATED,
                    checkpoint={"seed": "running", "seedIntent": recovery},
                )
                etag = write_remote_state(
                    operator, config, config_path, state, if_match=etag
                )
        else:
            raise LifecycleError("Synthetic seed requires a successful migration.")
        outputs = terraform_output(config, state, config_path, operator)
        services = output_value(outputs, "service_identifiers")
        if not isinstance(services, dict):
            raise LifecycleError("Identity outputs are incomplete.")
        pool = str(services["cognito_user_pool_id"])
        password = generated_password()
        try:
            existing = operator.call(
                "cognito-idp",
                "admin-get-user",
                "--user-pool-id",
                pool,
                "--username",
                username,
                allow_error_codes=("UserNotFoundException",),
            )
            if existing is not None:
                operator.call(
                    "cognito-idp",
                    "admin-delete-user",
                    "--user-pool-id",
                    pool,
                    "--username",
                    username,
                )
            operator.call(
                "s3api",
                "delete-object",
                "--bucket",
                config.state_bucket,
                "--key",
                config.secret_key,
            )
            operator.call(
                "cognito-idp",
                "admin-create-user",
                "--user-pool-id",
                pool,
                "--username",
                username,
                "--temporary-password",
                password,
                "--message-action",
                "SUPPRESS",
                "--user-attributes",
                "Name=email,Value=reviewer@synthetic.invalid",
                "Name=email_verified,Value=true",
                resource_delta=1,
            )
            operator.call(
                "cognito-idp",
                "admin-set-user-password",
                "--user-pool-id",
                pool,
                "--username",
                username,
                "--password",
                password,
                "--permanent",
            )
            operator.call(
                "cognito-idp",
                "admin-add-user-to-group",
                "--user-pool-id",
                pool,
                "--username",
                username,
                "--group-name",
                config.reviewer_group_name,
            )
            s3_put_json(
                operator,
                config,
                config.secret_key,
                {"schemaVersion": 1, "username": username, "password": password},
                runtime_directory(config_path) / "synthetic-reviewer-upload.json",
                if_none_match=True,
                resource_delta=1,
            )
        except LifecycleError as seed_error:
            state.record_failure("seed")
            state.checkpoints["seed"] = "failed"
            try:
                write_remote_state(operator, config, config_path, state, if_match=etag)
            except LifecycleError as checkpoint_error:
                seed_error.add_note(
                    "The seed failure checkpoint also failed safely; the exact "
                    "local recovery owner was retained."
                )
                raise seed_error from checkpoint_error
            raise
        state.checkpoints.pop("seedIntent", None)
        state.transition(Phase.SEEDED, checkpoint={"seed": "passed"})
        write_remote_state(operator, config, config_path, state, if_match=etag)
        try:
            seed_recovery_path(config_path).unlink(missing_ok=True)
        except OSError:
            pass
        effects = Effects()
        effects.add(source.effects)
        effects.add(operator.effects)
        result = {
            "phase": state.phase.value,
            "syntheticReviewer": "created",
            "syntheticApplicationData": "bounded-by-smoke",
            **effects.result(),
        }
        assert_public_safe(result)
        return result


def command_smoke(
    config: LifecycleConfig, config_path: Path, source: AwsCli
) -> dict[str, object]:
    verify_source(config, source)
    operator = assume_role(source, config, "operator_deployment", "portfolio-smoke")
    remote = read_remote_state(operator, config, config_path)
    if remote is None:
        raise LifecycleError("Remote lifecycle is missing.")
    state, etag = remote
    if state.phase == Phase.FAILED and state.last_failure is not None:
        if state.last_failure.get("operation") != "smoke":
            raise LifecycleError("A different failed operation owns this lifecycle.")
        state.resume(Phase.SEEDED)
    if state.phase != Phase.SEEDED:
        raise LifecycleError("Authenticated smoke requires synthetic seed.")
    outputs = terraform_output(config, state, config_path, operator)
    endpoints = output_value(outputs, "public_endpoints")
    if not isinstance(endpoints, dict):
        raise LifecycleError("Public endpoint output is incomplete.")
    endpoint = str(endpoints.get("web_https", ""))
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.netloc:
        raise LifecycleError("Smoke endpoint is not generated AWS HTTPS.")
    secret_result = s3_get_json(
        operator,
        config,
        config.secret_key,
        runtime_directory(config_path) / "synthetic-reviewer-download.json",
    )
    if secret_result is None:
        raise LifecycleError("Synthetic reviewer credential is missing.")
    reviewer, _ = secret_result
    env = dict(os.environ)
    env.update(
        {
            "PORTFOLIO_AWS_SMOKE_BASE_URL": endpoint,
            "PORTFOLIO_AWS_SMOKE_USERNAME": str(reviewer.get("username", "")),
            "PORTFOLIO_AWS_SMOKE_PASSWORD": str(reviewer.get("password", "")),
            "PORTFOLIO_AWS_SMOKE_RESOURCE": config.oidc_api_audience,
            "PORTFOLIO_AWS_SMOKE_OUTPUT": str(
                runtime_directory(config_path) / "smoke-result.json"
            ),
        }
    )
    pnpm = require_command("pnpm")
    pnpm_command = [pnpm]
    if os.name == "nt" and Path(pnpm).suffix.lower() in {".cmd", ".bat"}:
        pnpm_command = [require_command("cmd"), "/d", "/c", pnpm]
    state.transition(Phase.SEEDED, checkpoint={"smoke": "running"})
    etag = write_remote_state(operator, config, config_path, state, if_match=etag)
    required = {
        "externalHttps": True,
        "authorizationCodePkce": True,
        "accessTokenSession": True,
        "upload": True,
        "asynchronousCompletion": True,
        "reviewDecision": True,
        "resourceBoundAudience": True,
        "auditHistory": True,
        "sourcePrivate": True,
    }
    try:
        run_process(
            [
                *pnpm_command,
                "exec",
                "playwright",
                "test",
                "--config",
                "playwright.aws.config.ts",
            ],
            env=env,
            timeout=600,
            label="Authenticated external AWS smoke",
        )
        smoke = load_json(runtime_directory(config_path) / "smoke-result.json")
        if any(smoke.get(key) != expected for key, expected in required.items()):
            raise LifecycleError("Authenticated AWS smoke evidence was incomplete.")
    except (LifecycleError, subprocess.TimeoutExpired) as smoke_error:
        state.record_failure("smoke")
        state.checkpoints["smoke"] = "failed"
        try:
            write_remote_state(operator, config, config_path, state, if_match=etag)
        except LifecycleError as checkpoint_error:
            smoke_error.add_note(
                "The authenticated smoke failure checkpoint also failed safely."
            )
            raise smoke_error from checkpoint_error
        raise
    state.transition(Phase.SMOKE_PASSED, checkpoint={"smoke": "passed"})
    write_remote_state(operator, config, config_path, state, if_match=etag)
    effects = Effects()
    effects.add(source.effects)
    effects.add(operator.effects)
    result = {
        "phase": state.phase.value,
        "externalHttps": "passed",
        "authenticatedAsyncSmoke": "passed",
        "proofChecks": len(required),
        **effects.result(),
    }
    assert_public_safe(result)
    return result


def command_extend(
    config: LifecycleConfig,
    config_path: Path,
    source: AwsCli,
    minutes: int,
) -> dict[str, object]:
    verify_source(config, source)
    operator = assume_role(source, config, "operator_deployment", "portfolio-extend")
    remote = read_remote_state(operator, config, config_path)
    if remote is None:
        raise LifecycleError("Remote lifecycle is missing.")
    state, etag = remote
    intent = fallback_extend_intent(state, config, minutes)
    instant = utc_now()
    if intent is None:
        current = parse_time(str(state.fallback.get("expiresAt", "")))
        new_expiry = current + timedelta(minutes=minutes)
        state.validate_fallback_extension(new_expiry, now=instant)
        verify_schedule(operator, config, current)
        state.transition(
            state.phase,
            checkpoint={
                "fallbackExtendIntent": {
                    "scheduleName": config.schedule_name,
                    "currentExpiresAt": isoformat(current),
                    "newExpiresAt": isoformat(new_expiry),
                    "addedMinutes": minutes,
                }
            },
        )
        etag = write_remote_state(operator, config, config_path, state, if_match=etag)
    else:
        current, new_expiry = intent
    extension = reconcile_schedule_extension(
        operator,
        config,
        current,
        new_expiry,
        now=instant,
    )
    registered = parse_time(str(state.fallback.get("registeredAt", "")))
    state.set_fallback(
        schedule_name=config.schedule_name,
        registered_at=registered,
        expires_at=new_expiry,
    )
    state.checkpoints.pop("fallbackExtendIntent", None)
    state.transition(
        state.phase,
        checkpoint={"fallback": "verified", "fallbackExtension": extension},
    )
    write_remote_state(operator, config, config_path, state, if_match=etag)
    effects = Effects()
    effects.add(source.effects)
    effects.add(operator.effects)
    result = {
        "phase": state.phase.value,
        "fallback": "extended-and-verified",
        "addedMinutes": minutes,
        **effects.result(),
    }
    assert_public_safe(result)
    return result


def tag_filters(config: LifecycleConfig) -> list[str]:
    return [
        f"Name=tag:{key},Values={value}" for key, value in config.ownership_tags.items()
    ]


TAGGED_RESOURCE_INVENTORY_LABELS = {
    "ec2:vpc": "vpc",
    "ec2:subnet": "subnet",
    "ec2:security-group": "securityGroup",
    "ec2:security-group-rule": "securityGroup",
    "ec2:route-table": "routeTable",
    "ec2:internet-gateway": "internetGateway",
    "ec2:vpc-endpoint": "vpcEndpoint",
    "ec2:network-interface": "networkInterface",
    "rds:db": "database",
    "rds:subgrp": "databaseSubnetGroup",
    "mq:broker": "broker",
    "logs:log-group": "applicationLogGroup",
    "apigateway:apis": "apiGateway",
    "apigateway:vpclinks": "vpcLink",
    "cognito-idp:userpool": "cognitoUserPool",
    "servicediscovery:namespace": "cloudMapNamespace",
    "servicediscovery:service": "cloudMapService",
    "route53:hostedzone": "privateHostedZone",
    "ecs:cluster": "ecsCluster",
    "ecs:service": "ecsService",
    "ecs:task": "ecsTask",
    "ecs:task-definition": "activeTaskDefinition",
    "secretsmanager:secret": "runtimeSecret",
}


def tagged_resource_kind(arn: str) -> str:
    parts = arn.split(":", maxsplit=5)
    if len(parts) != 6:
        return "unknown"
    service = parts[2]
    resource = parts[5].lstrip("/")
    if service == "s3":
        return "s3:bucket"
    resource_type = resource.split("/", maxsplit=1)[0].split(":", maxsplit=1)[0]
    return f"{service}:{resource_type}"


def unresolved_tagged_resource_count(
    mappings: object, inventory: Mapping[str, int]
) -> int:
    if not isinstance(mappings, list):
        raise LifecycleError("Tagged resource inventory was not a list.")
    unresolved = 0
    for mapping in mappings:
        if not isinstance(mapping, dict):
            unresolved += 1
            continue
        kind = tagged_resource_kind(str(mapping.get("ResourceARN", "")))
        label = (
            "applicationBucket"
            if kind == "s3:bucket"
            else TAGGED_RESOURCE_INVENTORY_LABELS.get(kind)
        )
        # The Resource Groups Tagging API can retain mappings after the owning
        # service has already proved the resource absent. Unknown resource
        # kinds remain fail-closed; known kinds defer to the exact service probe.
        if label is None or inventory.get(label, 0) > 0:
            unresolved += 1
    return unresolved


def inventory_residue(client: AwsCli, config: LifecycleConfig) -> dict[str, int]:
    filters = tag_filters(config)
    inventory: dict[str, int] = {}
    ec2_calls = {
        "vpc": ("describe-vpcs", "Vpcs"),
        "subnet": ("describe-subnets", "Subnets"),
        "securityGroup": ("describe-security-groups", "SecurityGroups"),
        "routeTable": ("describe-route-tables", "RouteTables"),
        "internetGateway": ("describe-internet-gateways", "InternetGateways"),
        "vpcEndpoint": ("describe-vpc-endpoints", "VpcEndpoints"),
        "networkInterface": ("describe-network-interfaces", "NetworkInterfaces"),
    }
    for label, (operation, key) in ec2_calls.items():
        response = client.call("ec2", operation, "--filters", *filters) or {}
        inventory[label] = len(response.get(key, []))
    named_calls = (
        (
            "database",
            "rds",
            "describe-db-instances",
            "DBInstances",
            (
                "--db-instance-identifier",
                f"{config.name_prefix}-{config.environment}-postgresql",
            ),
            ("DBInstanceNotFound",),
        ),
        (
            "databaseSubnetGroup",
            "rds",
            "describe-db-subnet-groups",
            "DBSubnetGroups",
            ("--db-subnet-group-name", f"{config.name_prefix}-{config.environment}"),
            ("DBSubnetGroupNotFoundFault",),
        ),
        (
            "applicationBucket",
            "s3api",
            "head-bucket",
            "",
            ("--bucket", f"{config.name_prefix}-{config.environment}-documents"),
            ("404", "NoSuchBucket", "Not Found"),
        ),
    )
    for label, service, operation, key, arguments, missing in named_calls:
        response = client.call(
            service, operation, *arguments, allow_error_codes=missing
        )
        inventory[label] = (
            0 if response is None else (1 if not key else len(response.get(key, [])))
        )
    brokers = client.call("mq", "list-brokers") or {}
    inventory["broker"] = sum(
        1
        for broker in brokers.get("BrokerSummaries", [])
        if broker.get("BrokerName")
        == f"{config.name_prefix}-{config.environment}-rabbitmq"
    )
    logs = (
        client.call(
            "logs",
            "describe-log-groups",
            "--log-group-name-prefix",
            f"/portfolio/{config.name_prefix}/{config.environment}/",
        )
        or {}
    )
    inventory["applicationLogGroup"] = sum(
        1
        for group in logs.get("logGroups", [])
        if "/controller/" not in str(group.get("logGroupName", ""))
    )
    apis = client.call("apigatewayv2", "get-apis") or {}
    inventory["apiGateway"] = sum(
        1
        for api in apis.get("Items", [])
        if api.get("Name") == f"{config.name_prefix}-{config.environment}"
    )
    links = client.call("apigatewayv2", "get-vpc-links") or {}
    inventory["vpcLink"] = sum(
        1
        for link in links.get("Items", [])
        if link.get("Name") == f"{config.name_prefix}-{config.environment}"
    )
    pools = client.call("cognito-idp", "list-user-pools", "--max-results", "60") or {}
    inventory["cognitoUserPool"] = sum(
        1
        for pool in pools.get("UserPools", [])
        if pool.get("Name") == f"{config.name_prefix}-{config.environment}"
    )
    namespaces = client.call("servicediscovery", "list-namespaces") or {}
    inventory["cloudMapNamespace"] = sum(
        1
        for item in namespaces.get("Namespaces", [])
        if item.get("Name") == f"{config.name_prefix}-{config.environment}.internal"
    )
    services = client.call("servicediscovery", "list-services") or {}
    inventory["cloudMapService"] = sum(
        1 for item in services.get("Services", []) if item.get("Name") in {"web", "api"}
    )
    zones = client.call("route53", "list-hosted-zones-by-name") or {}
    inventory["privateHostedZone"] = sum(
        1
        for zone in zones.get("HostedZones", [])
        if str(zone.get("Name", "")).rstrip(".")
        == f"{config.name_prefix}-{config.environment}.internal"
    )
    clusters = client.call("ecs", "list-clusters") or {}
    inventory["ecsCluster"] = sum(
        1
        for arn in clusters.get("clusterArns", [])
        if str(arn).endswith(f"/{config.name_prefix}-{config.environment}")
    )
    cluster_name = f"{config.name_prefix}-{config.environment}"
    if inventory["ecsCluster"]:
        services = client.call("ecs", "list-services", "--cluster", cluster_name) or {}
        inventory["ecsService"] = sum(
            1
            for arn in services.get("serviceArns", [])
            if str(arn).endswith(f"/{cluster_name}/{cluster_name}-web")
            or str(arn).endswith(f"/{cluster_name}/{cluster_name}-api")
            or str(arn).endswith(f"/{cluster_name}/{cluster_name}-ml")
        )
        tasks = client.call("ecs", "list-tasks", "--cluster", cluster_name) or {}
        inventory["ecsTask"] = len(tasks.get("taskArns", []))
    else:
        inventory["ecsService"] = 0
        inventory["ecsTask"] = 0
    task_definitions = (
        client.call(
            "ecs",
            "list-task-definitions",
            "--family-prefix",
            f"{config.name_prefix}-{config.environment}-",
            "--status",
            "ACTIVE",
        )
        or {}
    )
    inventory["activeTaskDefinition"] = len(
        task_definitions.get("taskDefinitionArns", [])
    )
    secrets_response = (
        client.call(
            "secretsmanager",
            "list-secrets",
            "--filters",
            f"Key=name,Values={config.name_prefix}-{config.environment}-",
            "--include-planned-deletion",
        )
        or {}
    )
    inventory["runtimeSecret"] = sum(
        1
        for item in secrets_response.get("SecretList", [])
        if str(item.get("Name", "")).startswith(
            f"{config.name_prefix}-{config.environment}-"
        )
    )
    tagged = (
        client.call(
            "resourcegroupstaggingapi",
            "get-resources",
            "--tag-filters",
            *[
                f"Key={key},Values={value}"
                for key, value in config.ownership_tags.items()
            ],
        )
        or {}
    )
    inventory["tagInventory"] = unresolved_tagged_resource_count(
        tagged.get("ResourceTagMappingList", []), inventory
    )
    for purpose in ("web", "api", "ml"):
        response = client.call(
            "ecr",
            "describe-images",
            "--repository-name",
            f"{config.name_prefix}/{purpose}",
            "--image-ids",
            f"imageTag={config.image_tag}",
            allow_error_codes=("ImageNotFoundException",),
        )
        inventory[f"immutableImage{purpose.title()}"] = (
            0 if response is None else len(response.get("imageDetails", []))
        )
    return inventory


def terraform_destroy(
    config: LifecycleConfig,
    state: LifecycleState,
    config_path: Path,
    destroy: AwsCli,
) -> None:
    terraform = require_command("terraform")
    environment_root, tfvars, _ = terraform_init(config, state, config_path, destroy)
    terraform_env = terraform_environment(config, destroy)
    listed = run_process(
        [
            terraform,
            f"-chdir={environment_root}",
            "state",
            "list",
        ],
        env=terraform_env,
        timeout=300,
        label="Terraform managed environment state inventory",
        safe_failure_prefix="Error:",
    )
    managed_secret_versions = {
        "module.managed_state.aws_secretsmanager_secret_version.broker",
        "module.managed_state.aws_secretsmanager_secret_version.database",
    }
    for address in sorted(
        managed_secret_versions.intersection(listed.stdout.splitlines())
    ):
        run_process(
            [
                terraform,
                f"-chdir={environment_root}",
                "state",
                "rm",
                address,
            ],
            env=terraform_env,
            timeout=300,
            label="Terraform managed secret-version state detachment",
            safe_failure_prefix="Error:",
        )
    run_process(
        [
            terraform,
            f"-chdir={environment_root}",
            "destroy",
            "-input=false",
            "-auto-approve",
            "-refresh=false",
            f"-var-file={tfvars}",
        ],
        env=terraform_env,
        timeout=3600,
        label="Terraform managed environment destroy",
        safe_failure_prefix="Error:",
    )


def cleanup_published_images(
    config: LifecycleConfig, state: LifecycleState, destroy: AwsCli
) -> None:
    for purpose in ("web", "api", "ml"):
        described = destroy.call(
            "ecr",
            "describe-images",
            "--repository-name",
            f"{config.name_prefix}/{purpose}",
            "--image-ids",
            f"imageTag={config.image_tag}",
            allow_error_codes=("ImageNotFoundException",),
        )
        if described is None:
            continue
        details = described.get("imageDetails", [])
        if not details:
            continue
        if len(details) != 1:
            raise LifecycleError("Exact immutable image inventory was ambiguous.")
        digest = str(details[0].get("imageDigest", ""))
        checkpoint_digest = state.images.get(purpose)
        if checkpoint_digest is not None and digest != checkpoint_digest:
            raise LifecycleError("Immutable image digest drifted before cleanup.")
        response = (
            destroy.call(
                "ecr",
                "batch-delete-image",
                "--repository-name",
                f"{config.name_prefix}/{purpose}",
                "--image-ids",
                f"imageTag={config.image_tag}",
            )
            or {}
        )
        failures = response.get("failures", [])
        unexpected = [
            failure
            for failure in failures
            if not isinstance(failure, dict)
            or failure.get("failureCode") != "ImageNotFound"
        ]
        if unexpected:
            raise LifecycleError("Exact immutable image cleanup failed safely.")


def application_resources_possible(state: LifecycleState) -> bool:
    checkpoint = state.checkpoints.get("applicationResourcesPossible")
    if isinstance(checkpoint, bool):
        return checkpoint
    phase = state.phase
    if phase == Phase.FAILED and state.last_failure is not None:
        phase = Phase(state.last_failure["fromPhase"])
    return phase in {
        Phase.APPLYING,
        Phase.APPLIED,
        Phase.MIGRATED,
        Phase.SEEDED,
        Phase.SMOKE_PASSED,
        Phase.DESTROYING,
    }


def finalize_zero_residue(
    config: LifecycleConfig,
    config_path: Path,
    destroy: AwsCli,
    state: LifecycleState,
    etag: str,
) -> dict[str, int]:
    cleanup_published_images(config, state, destroy)
    inventory = inventory_residue(destroy, config)
    if any(inventory.values()):
        state.record_failure("sweep")
        state.checkpoints["residue"] = "present"
        write_remote_state(destroy, config, config_path, state, if_match=etag)
        raise LifecycleError("Service-specific residual inventory is not zero.")
    state.transition(Phase.ZERO_RESIDUE, checkpoint={"residue": "zero"})
    write_remote_state(destroy, config, config_path, state, if_match=etag)
    cleanup_completed_controls(config, destroy)
    return inventory


def cleanup_completed_controls(config: LifecycleConfig, destroy: AwsCli) -> None:
    destroy.call(
        "scheduler",
        "delete-schedule",
        "--name",
        config.schedule_name,
        "--group-name",
        config.schedule_group_name,
        allow_error_codes=("ResourceNotFoundException",),
    )
    for key in (config.secret_key, config.lease_key, config.configuration_key):
        destroy.call(
            "s3api",
            "delete-object",
            "--bucket",
            config.state_bucket,
            "--key",
            key,
        )


def command_destroy(
    config: LifecycleConfig,
    config_path: Path,
    source: AwsCli,
    *,
    mode: str,
) -> dict[str, object]:
    verify_source(config, source)
    operator = assume_role(
        source, config, "operator_deployment", "portfolio-destroy-control"
    )
    remote = read_remote_state(operator, config, config_path)
    if remote is None:
        raise LifecycleError("Remote lifecycle is missing.")
    state, etag = remote
    if state.phase == Phase.ZERO_RESIDUE:
        destroy = assume_role(
            operator, config, "destroy", "portfolio-completed-cleanup"
        )
        cleanup_completed_controls(config, destroy)
        effects = Effects()
        for client in (source, operator, destroy):
            effects.add(client.effects)
        result = {
            "phase": Phase.ZERO_RESIDUE.value,
            "destroy": "completed-control-cleanup",
            "residualResources": 0,
            **effects.result(),
        }
        assert_public_safe(result)
        return result
    if mode == "scheduled":
        expiry = utc_now() + timedelta(minutes=2)
        operator.call(
            "scheduler",
            "update-schedule",
            "--name",
            config.schedule_name,
            "--group-name",
            config.schedule_group_name,
            "--schedule-expression",
            schedule_expression(expiry),
            "--schedule-expression-timezone",
            "UTC",
            "--flexible-time-window",
            '{"Mode":"OFF"}',
            "--action-after-completion",
            "NONE",
            "--state",
            "ENABLED",
            "--target",
            schedule_target(config),
        )
        verify_schedule(operator, config, expiry)
        effects = Effects()
        effects.add(source.effects)
        effects.add(operator.effects)
        result = {
            "phase": state.phase.value,
            "destroy": "scheduled-controller-armed",
            "fallback": "retained-until-zero-residue",
            **effects.result(),
        }
        assert_public_safe(result)
        return result
    destroy = assume_role(operator, config, "destroy", "portfolio-manual-destroy")
    may_have_application_resources = application_resources_possible(state)
    state.transition(
        Phase.DESTROYING,
        checkpoint={
            "destroy": "running",
            "applicationResourcesPossible": may_have_application_resources,
        },
    )
    etag = write_remote_state(operator, config, config_path, state, if_match=etag)
    try:
        if may_have_application_resources:
            terraform_destroy(config, state, config_path, destroy)
        inventory = finalize_zero_residue(config, config_path, destroy, state, etag)
    except LifecycleError:
        state.record_failure("destroy")
        state.checkpoints["destroy"] = "failed"
        try:
            write_remote_state(destroy, config, config_path, state, if_match=etag)
        except LifecycleError:
            pass
        raise
    effects = Effects()
    for client in (source, operator, destroy):
        effects.add(client.effects)
    result = {
        "phase": Phase.ZERO_RESIDUE.value,
        "destroy": "passed",
        "residualCategories": len(inventory),
        "residualResources": 0,
        "fallback": "removed-after-zero-residue",
        **effects.result(),
    }
    assert_public_safe(result)
    return result


def command_controller_destroy(
    config: LifecycleConfig, config_path: Path, codebuild: AwsCli
) -> dict[str, object]:
    identity = codebuild.call("sts", "get-caller-identity") or {}
    expected = (
        f"arn:{config.partition}:sts::{config.account_id}:assumed-role/"
        f"{config.name_prefix}-{config.environment}-codebuild-destroy/"
    )
    if not str(identity.get("Arn", "")).startswith(expected):
        raise LifecycleError("Fallback did not start from the exact CodeBuild role.")
    remote = read_remote_state(codebuild, config, config_path)
    if remote is None:
        raise LifecycleError("Fallback lifecycle configuration is missing.")
    state, etag = remote
    destroy = assume_role(codebuild, config, "destroy", "portfolio-fallback-destroy")
    if state.phase == Phase.ZERO_RESIDUE:
        cleanup_completed_controls(config, destroy)
        effects = Effects()
        effects.add(codebuild.effects)
        effects.add(destroy.effects)
        result = {
            "phase": Phase.ZERO_RESIDUE.value,
            "destroy": "automatic-control-cleanup",
            "residualResources": 0,
            **effects.result(),
        }
        assert_public_safe(result)
        return result
    may_have_application_resources = application_resources_possible(state)
    state.transition(
        Phase.DESTROYING,
        checkpoint={
            "destroy": "running-controller",
            "applicationResourcesPossible": may_have_application_resources,
        },
    )
    etag = write_remote_state(destroy, config, config_path, state, if_match=etag)
    try:
        if may_have_application_resources:
            terraform_destroy(config, state, config_path, destroy)
        inventory = finalize_zero_residue(config, config_path, destroy, state, etag)
    except LifecycleError:
        if state.phase != Phase.FAILED:
            state.record_failure("controller-destroy")
            state.checkpoints["destroy"] = "failed-controller"
            try:
                write_remote_state(destroy, config, config_path, state, if_match=etag)
            except LifecycleError:
                pass
        raise
    effects = Effects()
    effects.add(codebuild.effects)
    effects.add(destroy.effects)
    result = {
        "phase": Phase.ZERO_RESIDUE.value,
        "destroy": "automatic-controller-passed",
        "residualCategories": len(inventory),
        "residualResources": 0,
        **effects.result(),
    }
    assert_public_safe(result)
    return result


def command_status(
    config: LifecycleConfig, config_path: Path, source: AwsCli
) -> dict[str, object]:
    verify_source(config, source)
    operator = assume_role(source, config, "operator_deployment", "portfolio-status")
    remote = read_remote_state(operator, config, config_path, allow_missing=True)
    state = None if remote is None else remote[0]
    status = sanitized_status(state)
    if state is not None and state.fallback.get("verified"):
        expiry = parse_time(str(state.fallback["expiresAt"]))
        schedule = read_schedule(operator, config)
        instant = utc_now()
        if schedule is None:
            status["fallback"] = "expired-or-missing"
        else:
            try:
                verify_schedule_payload(schedule, config, expiry)
            except LifecycleError:
                status["fallback"] = "drifted"
            else:
                status["fallback"] = (
                    "verified" if expiry > instant else "expired-or-missing"
                )
        status["fallbackExpiresAt"] = isoformat(expiry)
        status["fallbackRemainingMinutes"] = max(
            0, int((expiry - instant).total_seconds() // 60)
        )
    if state is not None and application_resources_possible(state):
        services = (
            operator.call(
                "ecs",
                "describe-services",
                "--cluster",
                f"{config.name_prefix}-{config.environment}",
                "--services",
                *[
                    f"{config.name_prefix}-{config.environment}-{purpose}"
                    for purpose in ("web", "api", "ml")
                ],
            )
            or {}
        )
        service_items = [
            item for item in services.get("services", []) if isinstance(item, dict)
        ]
        desired = sum(int(item.get("desiredCount", 0)) for item in service_items)
        running = sum(int(item.get("runningCount", 0)) for item in service_items)
        failures = services.get("failures", [])
        status["ecsServices"] = len(service_items)
        status["ecsDesiredTasks"] = desired
        status["ecsRunningTasks"] = running
        status["ecsHealth"] = (
            "ready"
            if len(service_items) == 3
            and not failures
            and desired > 0
            and running == desired
            else "not-ready"
        )
    effects = Effects()
    effects.add(source.effects)
    effects.add(operator.effects)
    result = {**status, **effects.result()}
    assert_public_safe(result)
    return result


def command_sweep(
    config: LifecycleConfig, config_path: Path, source: AwsCli
) -> dict[str, object]:
    verify_source(config, source)
    operator = assume_role(
        source, config, "operator_deployment", "portfolio-sweep-control"
    )
    destroy = assume_role(operator, config, "destroy", "portfolio-sweep")
    inventory = inventory_residue(destroy, config)
    effects = Effects()
    for client in (source, operator, destroy):
        effects.add(client.effects)
    result = {
        "residualCategories": len(inventory),
        "residualResources": sum(inventory.values()),
        "zeroResidue": not any(inventory.values()),
        **effects.result(),
    }
    assert_public_safe(result)
    if any(inventory.values()):
        raise LifecycleError("Service-specific residual inventory is not zero.")
    return result


def command_deploy(
    config: LifecycleConfig,
    config_path: Path,
    source: AwsCli,
    ttl_minutes: int,
) -> dict[str, object]:
    verify_source(config, source)
    observer = assume_role(
        source, config, "operator_deployment", "portfolio-deploy-state"
    )
    operations = {
        "publish-images": lambda: command_publish_images(config, config_path, source),
        "register-fallback": lambda: command_register_fallback(
            config, config_path, source, ttl_minutes
        ),
        "apply": lambda: command_apply(config, config_path, source),
        "migrate": lambda: command_migrate(config, config_path, source),
        "seed": lambda: command_seed(config, config_path, source),
        "smoke": lambda: command_smoke(config, config_path, source),
    }
    results = []
    for _ in range(7):
        remote = read_remote_state(observer, config, config_path, allow_missing=True)
        state = None if remote is None else remote[0]
        if state is None or state.phase in {Phase.CONFIGURED, Phase.PREFLIGHTED}:
            operation_name = "publish-images"
        elif state.phase == Phase.IMAGES_PUBLISHED:
            operation_name = "register-fallback"
        elif state.phase == Phase.FALLBACK_REGISTERED:
            operation_name = "apply"
        elif state.phase == Phase.APPLIED:
            operation_name = "migrate"
        elif state.phase == Phase.MIGRATED:
            operation_name = "seed"
        elif state.phase == Phase.SEEDED:
            operation_name = "smoke"
        elif state.phase == Phase.SMOKE_PASSED:
            break
        elif state.phase == Phase.FAILED and state.last_failure is not None:
            operation_name = str(state.last_failure.get("operation"))
            if operation_name not in {"publish-images", "migrate", "seed", "smoke"}:
                raise LifecycleError(
                    "This failed boundary requires verified destroy before retry."
                )
        else:
            raise LifecycleError("Lifecycle phase cannot be resumed by deploy.")
        results.append(operations[operation_name]())
    else:
        raise LifecycleError("Deployment resume loop exceeded its bounded phases.")
    result = {
        "phase": Phase.SMOKE_PASSED.value,
        "operations": len(results),
        "fallback": "retained",
        "authenticatedAsyncSmoke": "passed",
    }
    assert_public_safe(result)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Operate the bounded Portfolio AWS lifecycle"
    )
    parser.add_argument(
        "--aws-cli", default=shutil.which("aws") or "aws", help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=REPOSITORY_ROOT
        / ".git"
        / "portfolio-aws-lifecycle"
        / "manual"
        / "config.json",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    configure = subparsers.add_parser("configure")
    configure.add_argument("--repository-identity", default=DEFAULT_REPOSITORY)
    configure.add_argument("--name-prefix", default=DEFAULT_PREFIX)
    configure.add_argument("--environment", default=DEFAULT_ENVIRONMENT)
    configure.add_argument(
        "--caller-mode",
        choices=(CALLER_MODE_SOURCE_USER, CALLER_MODE_GITHUB_AUTOMATION),
        default=CALLER_MODE_SOURCE_USER,
    )
    configure.add_argument(
        "--automation-event", choices=("workflow_dispatch", "schedule")
    )
    configure.add_argument("--region", default=DEFAULT_REGION)
    configure.add_argument(
        "--availability-zones",
        nargs=2,
        default=[f"{DEFAULT_REGION}a", f"{DEFAULT_REGION}b"],
    )
    configure.add_argument("--state-bucket")
    configure.add_argument(
        "--oidc-api-audience", default="https://api.reactorfront.invalid/api"
    )
    for name in (
        "preflight",
        "publish-images",
        "apply",
        "migrate",
        "seed",
        "smoke",
        "status",
        "sweep",
        "controller-destroy",
    ):
        subparsers.add_parser(name)
    fallback = subparsers.add_parser("register-fallback")
    fallback.add_argument("--ttl-minutes", type=int, default=60, choices=range(15, 121))
    extend = subparsers.add_parser("extend")
    extend.add_argument("--minutes", type=int, required=True)
    destroy = subparsers.add_parser("destroy")
    destroy.add_argument("--mode", choices=("manual", "scheduled"), default="manual")
    deploy = subparsers.add_parser("deploy")
    deploy.add_argument("--ttl-minutes", type=int, default=60, choices=range(15, 121))
    return parser


def execute(args: argparse.Namespace) -> dict[str, object]:
    source = AwsCli(args.aws_cli)
    if args.command == "configure":
        return command_configure(args, source)
    config = load_config(args.config)
    commands = {
        "preflight": lambda: command_preflight(config, args.config, source),
        "publish-images": lambda: command_publish_images(config, args.config, source),
        "register-fallback": lambda: command_register_fallback(
            config, args.config, source, args.ttl_minutes
        ),
        "apply": lambda: command_apply(config, args.config, source),
        "migrate": lambda: command_migrate(config, args.config, source),
        "seed": lambda: command_seed(config, args.config, source),
        "smoke": lambda: command_smoke(config, args.config, source),
        "extend": lambda: command_extend(config, args.config, source, args.minutes),
        "destroy": lambda: command_destroy(config, args.config, source, mode=args.mode),
        "controller-destroy": lambda: command_controller_destroy(
            config, args.config, source
        ),
        "status": lambda: command_status(config, args.config, source),
        "sweep": lambda: command_sweep(config, args.config, source),
        "deploy": lambda: command_deploy(config, args.config, source, args.ttl_minutes),
    }
    return commands[args.command]()


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = execute(args)
        assert_public_safe(result)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (LifecycleError, OSError, subprocess.TimeoutExpired) as error:
        print(f"AWS lifecycle failed safely: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
