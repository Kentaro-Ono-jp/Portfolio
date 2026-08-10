from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import string
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

from aws_lifecycle_core import (
    LifecycleConfig,
    LifecycleError,
    LifecycleState,
    Phase,
    assert_public_safe,
    canonical_json,
    isoformat,
    parse_time,
    sanitized_status,
    sha256_file,
    sha256_json,
    utc_now,
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


WRITE_OPERATIONS = {
    "s3api:put-object",
    "s3api:delete-object",
    "codebuild:start-build",
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
        raise LifecycleError(f"{label} failed; private diagnostics were suppressed.")
    return result


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


def derive_config(args: argparse.Namespace, source: AwsCli) -> LifecycleConfig:
    identity = source.call("sts", "get-caller-identity") or {}
    account_id = str(identity.get("Account", ""))
    partition = "aws"
    expected_source = f"arn:{partition}:iam::{account_id}:user/{SOURCE_USER_NAME}"
    if identity.get("Arn") != expected_source:
        raise LifecycleError(
            "Active credential is not the exact Portfolio source user."
        )
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
    accepted = {
        config.repository_url,
        f"git@github.com:{config.repository_identity}.git",
    }
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
    if identity.get("Arn") != source_user_arn(config):
        raise LifecycleError(
            "Active source credential is not the exact configured user."
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
            "--state-bucket-name",
            config.state_bucket,
        ],
        timeout=300,
        label="Frozen static IAM attestation",
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


def verify_controller(config: LifecycleConfig, operator: AwsCli) -> None:
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
        if (
            project.get("serviceRole") != role_arn(config, role_purpose)
            or source.get("type") != "NO_SOURCE"
            or str(source.get("buildspec", "")).replace("\r\n", "\n").strip()
            != expected_buildspec.replace("\r\n", "\n").strip()
            or artifacts.get("type") != "NO_ARTIFACTS"
            or project.get("buildTimeoutInMinutes") != 60
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
    path = config_path.parent / "runtime"
    path.mkdir(parents=True, exist_ok=True)
    return path


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
    )
    shown = run_process(
        [terraform, f"-chdir={environment_root}", "show", "-json", str(plan)],
        env=terraform_environment(config, session),
        timeout=300,
        label="Terraform plan inspection",
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
    verify_controller(config, operator)
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
    namespaces = operator.call("servicediscovery", "list-namespaces") or {}
    services = operator.call("servicediscovery", "list-services") or {}
    if namespaces.get("Namespaces") or services.get("Services"):
        raise LifecycleError("Cloud Map is not empty; owner review is required.")
    proof = {
        "sourceIdentity": "verified",
        "operatorSession": "verified",
        "staticIam": "verified",
        "persistentController": "verified",
        "persistentImageRepositories": 3,
        "persistentStateBucket": "verified",
        "sourceRevision": config.source_sha,
        "region": config.region,
        "cloudMapIsolation": "empty",
        "remoteControlObjects": 1 if lease_state == "recovered-exact" else 0,
        "lifecycleLease": lease_state,
        "readOnly": True,
        "staticIamReadCalls": int(static.get("attestationAwsReadCalls", 0)),
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
    verify_controller(config, operator)
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
        state.record_failure("publish-images")
        write_remote_state(operator, config, config_path, state, if_match=etag)
        raise LifecycleError("Image build did not return an exact build identity.")
    try:
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
        state.set_images(images)
        state.transition(
            Phase.IMAGES_PUBLISHED,
            checkpoint={"imageBuild": "passed"},
        )
        write_remote_state(operator, config, config_path, state, if_match=etag)
    except LifecycleError:
        state.record_failure("publish-images")
        write_remote_state(operator, config, config_path, state, if_match=etag)
        raise
    effects = Effects()
    effects.add(source.effects)
    effects.add(probe.effects)
    effects.add(operator.effects)
    result = {
        "phase": state.phase.value,
        "sourceRevision": config.source_sha,
        "immutableImages": len(state.images),
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


def verify_schedule(
    client: AwsCli, config: LifecycleConfig, expected_expiry: datetime
) -> None:
    schedule = (
        client.call(
            "scheduler",
            "get-schedule",
            "--name",
            config.schedule_name,
            "--group-name",
            "default",
        )
        or {}
    )
    if (
        schedule.get("State") != "ENABLED"
        or schedule.get("ScheduleExpression") != schedule_expression(expected_expiry)
        or schedule.get("ActionAfterCompletion") != "NONE"
        or schedule.get("Target", {}).get("Arn") != project_arn(config, "destroy")
        or schedule.get("Target", {}).get("RoleArn") != role_arn(config, "scheduler")
    ):
        raise LifecycleError("Fallback schedule read-back drifted.")


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
    remote = read_remote_state(operator, config, config_path)
    if remote is None:
        raise LifecycleError("Remote lifecycle is missing.")
    state, etag = remote
    if state.phase != Phase.IMAGES_PUBLISHED:
        raise LifecycleError("Fallback registration requires published images.")
    state.plan = create_plan(config, state, config_path, operator)
    registered = utc_now()
    expiry = registered + timedelta(minutes=ttl_minutes)
    state.set_fallback(
        schedule_name=config.schedule_name,
        registered_at=registered,
        expires_at=expiry,
    )
    operator.call(
        "scheduler",
        "create-schedule",
        "--name",
        config.schedule_name,
        "--group-name",
        "default",
        "--schedule-expression",
        schedule_expression(expiry),
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
    verify_schedule(operator, config, expiry)
    state.transition(
        Phase.FALLBACK_REGISTERED,
        checkpoint={"fallback": "verified", "plan": "fresh"},
    )
    write_remote_state(operator, config, config_path, state, if_match=etag)
    effects = Effects()
    effects.add(source.effects)
    effects.add(operator.effects)
    result = {
        "phase": state.phase.value,
        "fallback": "verified",
        "ttlMinutes": ttl_minutes,
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
    response = (
        operator.call(
            "ecs",
            "run-task",
            "--cluster",
            str(services["ecs_cluster"]),
            "--task-definition",
            str(services["migration_task_definition"]),
            "--launch-type",
            "FARGATE",
            "--platform-version",
            "1.4.0",
            "--network-configuration",
            network_configuration,
            "--started-by",
            f"portfolio-{config.source_sha[:20]}",
            "--tags",
            canonical_json(tags),
            "--propagate-tags",
            "TASK_DEFINITION",
            resource_delta=1,
        )
        or {}
    )
    tasks = response.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != 1:
        raise LifecycleError("Migration did not start one exact ECS task.")
    task_arn = str(tasks[0].get("taskArn", ""))
    operator.wait(
        "ecs",
        "tasks-stopped",
        "--cluster",
        str(services["ecs_cluster"]),
        "--tasks",
        task_arn,
    )
    described = (
        operator.call(
            "ecs",
            "describe-tasks",
            "--cluster",
            str(services["ecs_cluster"]),
            "--tasks",
            task_arn,
        )
        or {}
    )
    stopped = described.get("tasks", [])
    containers = stopped[0].get("containers", []) if stopped else []
    if len(containers) != 1 or containers[0].get("exitCode") != 0:
        state.record_failure("migrate")
        state.checkpoints["migration"] = "failed"
        write_remote_state(operator, config, config_path, state, if_match=etag)
        raise LifecycleError("Migration task did not exit successfully.")
    state.transition(Phase.MIGRATED, checkpoint={"migration": "passed"})
    write_remote_state(operator, config, config_path, state, if_match=etag)
    effects = Effects()
    effects.add(source.effects)
    effects.add(operator.effects)
    result = {"phase": state.phase.value, "migration": "passed", **effects.result()}
    assert_public_safe(result)
    return result


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
    verify_source(config, source)
    operator = assume_role(source, config, "operator_deployment", "portfolio-seed")
    remote = read_remote_state(operator, config, config_path)
    if remote is None:
        raise LifecycleError("Remote lifecycle is missing.")
    state, etag = remote
    if state.phase == Phase.FAILED and state.last_failure is not None:
        if state.last_failure.get("operation") != "seed":
            raise LifecycleError("A different failed operation owns this lifecycle.")
        state.resume(Phase.MIGRATED)
    if state.phase != Phase.MIGRATED:
        raise LifecycleError("Synthetic seed requires a successful migration.")
    outputs = terraform_output(config, state, config_path, operator)
    services = output_value(outputs, "service_identifiers")
    if not isinstance(services, dict):
        raise LifecycleError("Identity outputs are incomplete.")
    pool = str(services["cognito_user_pool_id"])
    username = "reviewer@synthetic.invalid"
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
    except LifecycleError:
        state.record_failure("seed")
        state.checkpoints["seed"] = "failed"
        write_remote_state(operator, config, config_path, state, if_match=etag)
        raise
    state.transition(Phase.SEEDED, checkpoint={"seed": "passed"})
    write_remote_state(operator, config, config_path, state, if_match=etag)
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
            "PORTFOLIO_AWS_SMOKE_OUTPUT": str(
                runtime_directory(config_path) / "smoke-result.json"
            ),
        }
    )
    pnpm = require_command("pnpm")
    run_process(
        [
            pnpm,
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
    required = {
        "externalHttps": True,
        "authorizationCodePkce": True,
        "accessTokenSession": True,
        "upload": True,
        "asynchronousCompletion": True,
        "reviewDecision": True,
        "auditHistory": True,
        "sourcePrivate": True,
    }
    if any(smoke.get(key) != expected for key, expected in required.items()):
        state.record_failure("smoke")
        state.checkpoints["smoke"] = "failed"
        write_remote_state(operator, config, config_path, state, if_match=etag)
        raise LifecycleError("Authenticated AWS smoke evidence was incomplete.")
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
    current = parse_time(str(state.fallback.get("expiresAt", "")))
    new_expiry = current + timedelta(minutes=minutes)
    state.extend_fallback(new_expiry)
    operator.call(
        "scheduler",
        "update-schedule",
        "--name",
        config.schedule_name,
        "--group-name",
        "default",
        "--schedule-expression",
        schedule_expression(new_expiry),
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
    verify_schedule(operator, config, new_expiry)
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
    inventory["tagInventory"] = len(tagged.get("ResourceTagMappingList", []))
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
    run_process(
        [
            terraform,
            f"-chdir={environment_root}",
            "destroy",
            "-input=false",
            "-auto-approve",
            f"-var-file={tfvars}",
        ],
        env=terraform_environment(config, destroy),
        timeout=3600,
        label="Terraform managed environment destroy",
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
        "default",
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
            "default",
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
        schedule = operator.call(
            "scheduler",
            "get-schedule",
            "--name",
            config.schedule_name,
            "--group-name",
            "default",
            allow_error_codes=("ResourceNotFoundException",),
        )
        status["fallback"] = (
            "verified"
            if schedule is not None and expiry > utc_now()
            else "expired-or-missing"
        )
        status["fallbackExpiresAt"] = isoformat(expiry)
        status["fallbackRemainingMinutes"] = max(
            0, int((expiry - utc_now()).total_seconds() // 60)
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
    fallback.add_argument(
        "--ttl-minutes", type=int, default=120, choices=range(15, 121)
    )
    extend = subparsers.add_parser("extend")
    extend.add_argument("--minutes", type=int, required=True)
    destroy = subparsers.add_parser("destroy")
    destroy.add_argument("--mode", choices=("manual", "scheduled"), default="manual")
    deploy = subparsers.add_parser("deploy")
    deploy.add_argument("--ttl-minutes", type=int, default=120, choices=range(15, 121))
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
