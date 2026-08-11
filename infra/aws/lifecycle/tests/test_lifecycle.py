from __future__ import annotations

import json
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from aws_lifecycle_core import (  # noqa: E402
    CALLER_MODE_GITHUB_AUTOMATION,
    FORWARD_PHASES,
    LifecycleConfig,
    LifecycleError,
    LifecycleState,
    Phase,
    assert_public_safe,
    sanitized_status,
    sha256_json,
)
import aws_lifecycle as lifecycle  # noqa: E402


def configuration() -> LifecycleConfig:
    account = "111122223333"
    prefix = "reactorfront"
    environment = "manual"
    partition = "aws"
    region = "us-east-1"
    role_base = f"arn:{partition}:iam::{account}:role/{prefix}-{environment}"
    return LifecycleConfig(
        account_id=account,
        partition=partition,
        region=region,
        availability_zones=("us-east-1a", "us-east-1b"),
        name_prefix=prefix,
        environment=environment,
        repository_identity="example-owner/example-repository",
        repository_url="https://github.com/example-owner/example-repository.git",
        source_sha="1" * 40,
        state_bucket=f"{prefix}-{account}-{region}-state",
        state_key=f"environments/{environment}/terraform.tfstate",
        control_prefix=f"controls/{prefix}/{environment}",
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
            "image": f"{prefix}-{environment}-image-build",
            "destroy": f"{prefix}-{environment}-destroy",
        },
        ecr_repository_urls={
            purpose: (f"{account}.dkr.ecr.{region}.amazonaws.com/{prefix}/{purpose}")
            for purpose in ("web", "api", "ml")
        },
    )


def state_at(config: LifecycleConfig, target: Phase) -> LifecycleState:
    state = LifecycleState(config.source_sha, sha256_json(config.to_dict()))
    for phase in FORWARD_PHASES[1:]:
        state.transition(phase)
        if phase == target:
            return state
    raise AssertionError(f"Unsupported target phase: {target}")


def migration_outputs(config: LifecycleConfig) -> dict[str, object]:
    return {
        "service_identifiers": {
            "value": {
                "ecs_cluster": f"{config.name_prefix}-{config.environment}",
                "migration_task_definition": (
                    f"arn:{config.partition}:ecs:{config.region}:{config.account_id}:"
                    f"task-definition/{config.name_prefix}-{config.environment}-migration:1"
                ),
            }
        },
        "migration_network": {
            "value": {
                "subnet_ids": ["subnet-public-a", "subnet-public-b"],
                "security_group_id": "sg-api",
            }
        },
    }


class FakeAws:
    def __init__(self, identity: str = "") -> None:
        self.identity = identity
        self.env: dict[str, str] = {}
        self.effects = lifecycle.Effects()
        self.calls: list[tuple[str, str, tuple[str, ...]]] = []

    def call(self, service: str, operation: str, *arguments: str, **_: object):
        self.calls.append((service, operation, arguments))
        if service == "sts" and operation == "get-caller-identity":
            return {"Arn": self.identity}
        if service == "s3api" and operation == "head-object":
            return {"ETag": '"etag"'}
        if service == "ecr" and operation == "describe-images":
            repository = arguments[arguments.index("--repository-name") + 1]
            purpose = repository.rsplit("/", maxsplit=1)[-1]
            digit = {"web": "1", "api": "2", "ml": "3"}[purpose]
            return {"imageDetails": [{"imageDigest": "sha256:" + digit * 64}]}
        if service == "ecr" and operation == "batch-delete-image":
            return {"failures": []}
        return {}


def controller_project(
    config: LifecycleConfig, purpose: str, *, buildspec: str | None = None
) -> dict[str, object]:
    buildspec_name = (
        "image-build.buildspec.yml" if purpose == "image" else "destroy.buildspec.yml"
    )
    expected_buildspec = (
        REPOSITORY_ROOT / "infra" / "aws" / "lifecycle" / buildspec_name
    ).read_text(encoding="utf-8")
    return {
        "name": config.projects[purpose],
        "serviceRole": config.roles[
            "codebuild_image" if purpose == "image" else "codebuild_destroy"
        ],
        "source": {
            "type": "NO_SOURCE",
            "buildspec": expected_buildspec if buildspec is None else buildspec,
        },
        "artifacts": {"type": "NO_ARTIFACTS"},
        "timeoutInMinutes": 60,
        "queuedTimeoutInMinutes": 30,
        "autoRetryLimit": 0 if purpose == "image" else 2,
        "environment": {
            "computeType": "BUILD_GENERAL1_SMALL",
            "image": "aws/codebuild/standard:7.0",
            "type": "LINUX_CONTAINER",
            "imagePullCredentialsType": "CODEBUILD",
            "privilegedMode": purpose == "image",
            "environmentVariables": [
                {"name": name, "value": value}
                for name, value in lifecycle.expected_project_environment(
                    config
                ).items()
            ],
        },
        "logsConfig": {
            "cloudWatchLogs": {
                "status": "ENABLED",
                "groupName": (
                    f"/portfolio/{config.name_prefix}/{config.environment}/"
                    f"controller/{purpose}"
                ),
                "streamName": purpose,
            }
        },
        "tags": [
            {"key": name, "value": value}
            for name, value in {
                "PortfolioEnvironment": config.environment,
                "PortfolioLayer": "bootstrap",
                "PortfolioManaged": "true",
                "PortfolioPersistent": "true",
                "PortfolioPurpose": f"{purpose}-controller",
                "PortfolioRepository": config.repository_identity,
            }.items()
        ],
    }


class FakeControllerAws(FakeAws):
    def __init__(self, projects: list[dict[str, object]]) -> None:
        super().__init__()
        self.projects = {str(project["name"]): project for project in projects}

    def call(self, service: str, operation: str, *arguments: str, **_: object):
        self.calls.append((service, operation, arguments))
        if service == "codebuild" and operation == "batch-get-projects":
            names = arguments[arguments.index("--names") + 1 :]
            return {"projects": [self.projects[name] for name in names]}
        if service == "codebuild" and operation == "update-project":
            name = arguments[arguments.index("--name") + 1]
            source = json.loads(arguments[arguments.index("--source") + 1])
            self.projects[name]["source"] = source
            return {"project": self.projects[name]}
        return super().call(service, operation, *arguments)


class ImageInventoryAws(FakeAws):
    def __init__(
        self, images: dict[str, str], *, image_tag_override: str | None = None
    ) -> None:
        super().__init__()
        self.images = images
        self.image_tag_override = image_tag_override

    def call(self, service: str, operation: str, *arguments: str, **kwargs: object):
        if service == "ecr" and operation == "describe-images":
            self.calls.append((service, operation, arguments))
            repository = arguments[arguments.index("--repository-name") + 1]
            purpose = repository.rsplit("/", maxsplit=1)[-1]
            digest = self.images.get(purpose)
            image_tag = arguments[arguments.index("--image-ids") + 1].removeprefix(
                "imageTag="
            )
            image_tag = self.image_tag_override or image_tag
            return (
                None
                if digest is None
                else {
                    "imageDetails": [{"imageDigest": digest, "imageTags": [image_tag]}]
                }
            )
        return super().call(service, operation, *arguments, **kwargs)


class ScheduleAws(FakeAws):
    def __init__(self, registered: datetime) -> None:
        super().__init__()
        self.registered = registered
        self.schedule: dict[str, object] | None = None

    def call(self, service: str, operation: str, *arguments: str, **kwargs: object):
        if service == "scheduler" and operation == "get-schedule":
            self.calls.append((service, operation, arguments))
            return self.schedule
        if service == "scheduler" and operation == "create-schedule":
            self.calls.append((service, operation, arguments))
            self.schedule = {
                "Name": arguments[arguments.index("--name") + 1],
                "GroupName": arguments[arguments.index("--group-name") + 1],
                "CreationDate": self.registered.isoformat(),
                "State": "ENABLED",
                "ScheduleExpression": arguments[
                    arguments.index("--schedule-expression") + 1
                ],
                "ScheduleExpressionTimezone": arguments[
                    arguments.index("--schedule-expression-timezone") + 1
                ],
                "FlexibleTimeWindow": json.loads(
                    arguments[arguments.index("--flexible-time-window") + 1]
                ),
                "ActionAfterCompletion": arguments[
                    arguments.index("--action-after-completion") + 1
                ],
                "Target": json.loads(arguments[arguments.index("--target") + 1]),
            }
            return {}
        if service == "scheduler" and operation == "update-schedule":
            self.calls.append((service, operation, arguments))
            if self.schedule is None:
                raise AssertionError("Schedule must exist before update")
            self.schedule.update(
                {
                    "Name": arguments[arguments.index("--name") + 1],
                    "GroupName": arguments[arguments.index("--group-name") + 1],
                    "State": arguments[arguments.index("--state") + 1],
                    "ScheduleExpression": arguments[
                        arguments.index("--schedule-expression") + 1
                    ],
                    "ScheduleExpressionTimezone": arguments[
                        arguments.index("--schedule-expression-timezone") + 1
                    ],
                    "FlexibleTimeWindow": json.loads(
                        arguments[arguments.index("--flexible-time-window") + 1]
                    ),
                    "ActionAfterCompletion": arguments[
                        arguments.index("--action-after-completion") + 1
                    ],
                    "Target": json.loads(arguments[arguments.index("--target") + 1]),
                }
            )
            return {}
        return super().call(service, operation, *arguments, **kwargs)


SCHEDULE_DRIFT_CASES = (
    "name",
    "group",
    "state",
    "expression",
    "timezone",
    "flexible-window",
    "action-after-completion",
    "target-project",
    "target-role",
    "retry-event-age",
    "retry-attempts",
    "start-date",
    "end-date",
    "kms-key",
)


def drift_schedule(schedule: dict[str, object], case: str, expiry: datetime) -> None:
    if case == "name":
        schedule["Name"] = "foreign-destroy"
    elif case == "group":
        schedule["GroupName"] = "foreign-lifecycle"
    elif case == "state":
        schedule["State"] = "DISABLED"
    elif case == "expression":
        schedule["ScheduleExpression"] = lifecycle.schedule_expression(
            expiry + timedelta(minutes=1)
        )
    elif case == "timezone":
        schedule["ScheduleExpressionTimezone"] = "Asia/Tokyo"
    elif case == "flexible-window":
        schedule["FlexibleTimeWindow"] = {
            "Mode": "FLEXIBLE",
            "MaximumWindowInMinutes": 1,
        }
    elif case == "action-after-completion":
        schedule["ActionAfterCompletion"] = "DELETE"
    elif case in {
        "target-project",
        "target-role",
        "retry-event-age",
        "retry-attempts",
    }:
        target = dict(schedule["Target"])  # type: ignore[arg-type]
        if case == "target-project":
            target["Arn"] = "arn:aws:codebuild:us-east-1:111122223333:project/foreign"
        elif case == "target-role":
            target["RoleArn"] = "arn:aws:iam::111122223333:role/foreign"
        else:
            retry = dict(target["RetryPolicy"])
            retry[
                "MaximumEventAgeInSeconds"
                if case == "retry-event-age"
                else "MaximumRetryAttempts"
            ] += 1
            target["RetryPolicy"] = retry
        schedule["Target"] = target
    elif case == "start-date":
        schedule["StartDate"] = "2026-08-11T00:00:00Z"
    elif case == "end-date":
        schedule["EndDate"] = "2026-08-11T01:00:00Z"
    elif case == "kms-key":
        schedule["KmsKeyArn"] = "arn:aws:kms:us-east-1:111122223333:key/synthetic"
    else:
        raise AssertionError(f"Unknown schedule drift case: {case}")


class MigrationAws(FakeAws):
    def __init__(
        self,
        config: LifecycleConfig,
        *,
        exit_code: int = 0,
        described_task_definition: str | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.exit_code = exit_code
        self.described_task_definition = described_task_definition
        self.created_task_count = 0
        self.task_arn = (
            f"arn:{config.partition}:ecs:{config.region}:{config.account_id}:"
            f"task/{config.name_prefix}-{config.environment}/" + "a" * 32
        )
        self.request: tuple[str, ...] | None = None

    def call(self, service: str, operation: str, *arguments: str, **kwargs: object):
        if service == "ecs" and operation == "run-task":
            self.calls.append((service, operation, arguments))
            if self.request is None:
                self.request = arguments
                self.created_task_count += 1
            elif arguments != self.request:
                raise LifecycleError("Synthetic ECS client-token conflict.")
            return {"tasks": [{"taskArn": self.task_arn}], "failures": []}
        if service == "ecs" and operation == "describe-tasks":
            self.calls.append((service, operation, arguments))
            assert self.request is not None
            cluster = self.request[self.request.index("--cluster") + 1]
            task_definition = self.request[self.request.index("--task-definition") + 1]
            started_by = self.request[self.request.index("--started-by") + 1]
            tags = json.loads(self.request[self.request.index("--tags") + 1])
            return {
                "tasks": [
                    {
                        "taskArn": self.task_arn,
                        "clusterArn": (
                            f"arn:{self.config.partition}:ecs:{self.config.region}:"
                            f"{self.config.account_id}:cluster/{cluster}"
                        ),
                        "taskDefinitionArn": (
                            self.described_task_definition or task_definition
                        ),
                        "startedBy": started_by,
                        "launchType": "FARGATE",
                        "platformVersion": "1.4.0",
                        "lastStatus": "STOPPED",
                        "desiredStatus": "STOPPED",
                        "tags": tags,
                        "containers": [{"exitCode": self.exit_code}],
                    }
                ],
                "failures": [],
            }
        return super().call(service, operation, *arguments, **kwargs)

    def wait(self, service: str, waiter: str, *arguments: str) -> None:
        self.calls.append((service, f"wait:{waiter}", arguments))


class SeedCloud:
    def __init__(self) -> None:
        self.password: str | None = "old-password"
        self.secret: dict[str, object] | None = None


class SeedAws(FakeAws):
    def __init__(self, cloud: SeedCloud) -> None:
        super().__init__()
        self.cloud = cloud

    def call(self, service: str, operation: str, *arguments: str, **kwargs: object):
        if service == "cognito-idp":
            self.calls.append((service, operation, arguments))
            if operation == "admin-get-user":
                return None if self.cloud.password is None else {"Username": "reviewer"}
            if operation == "admin-delete-user":
                self.cloud.password = None
                return {}
            if operation == "admin-create-user":
                self.cloud.password = arguments[
                    arguments.index("--temporary-password") + 1
                ]
                return {}
            if operation == "admin-set-user-password":
                self.cloud.password = arguments[arguments.index("--password") + 1]
                return {}
            if operation == "admin-add-user-to-group":
                return {}
        if service == "s3api" and operation == "delete-object":
            self.calls.append((service, operation, arguments))
            self.cloud.secret = None
            return {}
        return super().call(service, operation, *arguments, **kwargs)


class SeedRemote:
    def __init__(self, config: LifecycleConfig) -> None:
        self.config = config
        self.payload = state_at(config, Phase.MIGRATED).to_dict(config)
        self.revision = 0

    def read(self) -> tuple[LifecycleState, str]:
        state = LifecycleState.from_dict(self.payload)[1]
        return state, f"etag-{self.revision}"

    def write(self, state: LifecycleState, if_match: str | None) -> str:
        if if_match != f"etag-{self.revision}":
            raise LifecycleError("Synthetic stale lifecycle ETag.")
        self.payload = state.to_dict(self.config)
        self.revision += 1
        return f"etag-{self.revision}"


class LifecycleContractTests(unittest.TestCase):
    def test_image_buildspec_only_is_reconciled_and_read_back(self) -> None:
        config = configuration()
        fake = FakeControllerAws(
            [
                controller_project(config, "image", buildspec="stale"),
                controller_project(config, "destroy"),
            ]
        )
        evidence = lifecycle.verify_controller_projects(
            config, fake, reconcile_image_buildspec=True
        )
        self.assertTrue(evidence["imageBuildspecReconciled"])
        self.assertEqual(
            [operation for _, operation, _ in fake.calls].count("update-project"),
            1,
        )
        self.assertNotEqual(
            evidence["previousBuildspecSha256"],
            evidence["currentBuildspecSha256"],
        )

    def test_controller_reconciliation_rejects_non_buildspec_drift(self) -> None:
        config = configuration()
        image = controller_project(config, "image", buildspec="stale")
        image["timeoutInMinutes"] = 61
        fake = FakeControllerAws([image, controller_project(config, "destroy")])
        with self.assertRaises(LifecycleError):
            lifecycle.verify_controller_projects(
                config, fake, reconcile_image_buildspec=True
            )
        self.assertNotIn(
            "update-project", [operation for _, operation, _ in fake.calls]
        )

    def test_controller_never_reconciles_destroy_buildspec(self) -> None:
        config = configuration()
        fake = FakeControllerAws(
            [
                controller_project(config, "image"),
                controller_project(config, "destroy", buildspec="stale"),
            ]
        )
        with self.assertRaises(LifecycleError):
            lifecycle.verify_controller_projects(
                config, fake, reconcile_image_buildspec=True
            )
        self.assertNotIn(
            "update-project", [operation for _, operation, _ in fake.calls]
        )

    def test_configuration_round_trip_and_exact_bindings(self) -> None:
        expected = configuration()
        actual = LifecycleConfig.from_dict(expected.to_dict())
        self.assertEqual(actual, expected)
        self.assertEqual(
            actual.configuration_key, "controls/reactorfront/manual/configuration.json"
        )
        self.assertEqual(actual.schedule_name, "reactorfront-manual-destroy")
        self.assertEqual(actual.schedule_group_name, "reactorfront-manual-lifecycle")

    def test_automation_event_is_bound_to_the_exact_environment(self) -> None:
        manual = replace(
            configuration(),
            caller_mode=CALLER_MODE_GITHUB_AUTOMATION,
            caller_event="workflow_dispatch",
        )
        self.assertEqual(LifecycleConfig.from_dict(manual.to_dict()), manual)

        monthly_base = configuration().to_dict()
        monthly_base["environment"] = "monthly"
        monthly_base["stateKey"] = "environments/monthly/terraform.tfstate"
        monthly_base["controlPrefix"] = "controls/reactorfront/monthly"
        monthly_base["callerMode"] = CALLER_MODE_GITHUB_AUTOMATION
        monthly_base["callerEvent"] = "schedule"
        monthly_base["roles"] = {
            purpose: arn.replace("-manual-", "-monthly-")
            for purpose, arn in monthly_base["roles"].items()  # type: ignore[union-attr]
        }
        monthly_base["projects"] = {
            purpose: name.replace("-manual-", "-monthly-")
            for purpose, name in monthly_base["projects"].items()  # type: ignore[union-attr]
        }
        monthly = LifecycleConfig.from_dict(monthly_base)
        self.assertEqual(monthly.environment, "monthly")
        self.assertEqual(monthly.caller_event, "schedule")

        crossed = monthly.to_dict()
        crossed["callerEvent"] = "workflow_dispatch"
        with self.assertRaisesRegex(LifecycleError, "exact environment"):
            LifecycleConfig.from_dict(crossed)

    def test_legacy_source_user_configuration_keeps_its_exact_digest_shape(
        self,
    ) -> None:
        legacy = configuration().to_dict()
        legacy["schemaVersion"] = 1
        del legacy["callerMode"]
        del legacy["callerEvent"]

        loaded = LifecycleConfig.from_dict(legacy)

        self.assertEqual(loaded.caller_mode, "source-user")
        self.assertIsNone(loaded.caller_event)
        self.assertEqual(loaded.to_dict(), legacy)

    def test_configuration_schema_rejects_json_booleans(self) -> None:
        for boolean_version in (True, False):
            with self.subTest(boolean_version=boolean_version):
                payload = configuration().to_dict()
                payload["schemaVersion"] = boolean_version
                with self.assertRaisesRegex(LifecycleError, "configuration schema"):
                    LifecycleConfig.from_dict(payload)
                with self.assertRaisesRegex(LifecycleError, "configuration schema"):
                    replace(
                        configuration(),
                        config_schema_version=boolean_version,
                    )

    def test_automation_source_requires_exact_role_and_session_shape(self) -> None:
        config = replace(
            configuration(),
            caller_mode=CALLER_MODE_GITHUB_AUTOMATION,
            caller_event="workflow_dispatch",
        )
        accepted = FakeAws(
            "arn:aws:sts::111122223333:assumed-role/"
            "reactorfront-automation/portfolio-github-123456"
        )
        lifecycle.verify_source(config, accepted)

        for rejected in (
            "arn:aws:sts::111122223333:assumed-role/reactorfront-automation/arbitrary",
            "arn:aws:sts::111122223333:assumed-role/foreign/portfolio-github-123456",
            "arn:aws:iam::111122223333:user/ReactorFrontNoel",
        ):
            with self.subTest(rejected=rejected), self.assertRaises(LifecycleError):
                lifecycle.verify_source(config, FakeAws(rejected))

    def test_source_user_mode_cannot_cross_into_monthly(self) -> None:
        payload = configuration().to_dict()
        payload["environment"] = "monthly"
        payload["stateKey"] = "environments/monthly/terraform.tfstate"
        payload["controlPrefix"] = "controls/reactorfront/monthly"
        payload["roles"] = {
            purpose: arn.replace("-manual-", "-monthly-")
            for purpose, arn in payload["roles"].items()  # type: ignore[union-attr]
        }
        payload["projects"] = {
            purpose: name.replace("-manual-", "-monthly-")
            for purpose, name in payload["projects"].items()  # type: ignore[union-attr]
        }

        with self.assertRaisesRegex(LifecycleError, "manual environment"):
            LifecycleConfig.from_dict(payload)

    def test_normal_ttl_defaults_to_one_hour_without_removing_other_values(
        self,
    ) -> None:
        parser = lifecycle.build_parser()
        self.assertEqual(parser.parse_args(["deploy"]).ttl_minutes, 60)
        self.assertEqual(
            parser.parse_args(["register-fallback"]).ttl_minutes,
            60,
        )
        self.assertEqual(
            parser.parse_args(["deploy", "--ttl-minutes", "90"]).ttl_minutes,
            90,
        )

    def test_configuration_rejects_foreign_state_and_roles(self) -> None:
        payload = configuration().to_dict()
        payload["stateKey"] = "environments/monthly/terraform.tfstate"
        with self.assertRaises(LifecycleError):
            LifecycleConfig.from_dict(payload)
        payload = configuration().to_dict()
        del payload["roles"]["destroy"]  # type: ignore[index]
        with self.assertRaises(LifecycleError):
            LifecycleConfig.from_dict(payload)

    def test_strict_phase_order_and_idempotent_same_phase(self) -> None:
        config = configuration()
        state = LifecycleState(config.source_sha, sha256_json(config.to_dict()))
        with self.assertRaises(LifecycleError):
            state.transition(Phase.IMAGES_PUBLISHED)
        state.transition(Phase.PREFLIGHTED)
        revision = state.revision
        state.transition(Phase.PREFLIGHTED, checkpoint={"preflight": "passed"})
        self.assertEqual(state.revision, revision)
        self.assertEqual(state.checkpoints["preflight"], "passed")

    def test_every_forward_write_boundary_requires_order(self) -> None:
        config = configuration()
        state = LifecycleState(config.source_sha, sha256_json(config.to_dict()))
        for target in (
            Phase.PREFLIGHTED,
            Phase.IMAGES_PUBLISHED,
            Phase.FALLBACK_REGISTERED,
            Phase.APPLYING,
            Phase.APPLIED,
            Phase.MIGRATED,
            Phase.SEEDED,
            Phase.SMOKE_PASSED,
            Phase.DESTROYING,
            Phase.ZERO_RESIDUE,
        ):
            state.transition(target)
        self.assertEqual(state.phase, Phase.ZERO_RESIDUE)

    def test_every_forward_write_boundary_round_trips_interruption(self) -> None:
        config = configuration()
        state = LifecycleState(config.source_sha, sha256_json(config.to_dict()))
        for index, phase in enumerate(FORWARD_PHASES[:-1]):
            if index:
                state.transition(phase)
            interrupted = LifecycleState.from_dict(state.to_dict(config))[1]
            interrupted.record_failure(f"boundary-{index}")
            restored = LifecycleState.from_dict(interrupted.to_dict(config))[1]
            self.assertEqual(restored.phase, Phase.FAILED)
            with self.assertRaises(LifecycleError):
                restored.resume(FORWARD_PHASES[index + 1])
            restored.resume(phase)
            self.assertEqual(restored.phase, phase)

    def test_failure_is_truthful_and_resume_is_exact(self) -> None:
        config = configuration()
        state = LifecycleState(config.source_sha, sha256_json(config.to_dict()))
        state.transition(Phase.PREFLIGHTED)
        state.record_failure("publish-images")
        self.assertEqual(state.phase, Phase.FAILED)
        with self.assertRaises(LifecycleError):
            state.resume(Phase.CONFIGURED)
        state.resume(Phase.PREFLIGHTED)
        self.assertIsNone(state.last_failure)

    def test_fallback_and_extend_never_exceed_two_hours(self) -> None:
        config = configuration()
        state = LifecycleState(config.source_sha, sha256_json(config.to_dict()))
        registered = datetime(2026, 8, 10, 0, 0, tzinfo=UTC)
        state.set_fallback(
            schedule_name=config.schedule_name,
            registered_at=registered,
            expires_at=registered + timedelta(minutes=60),
        )
        state.extend_fallback(
            registered + timedelta(minutes=119),
            now=registered + timedelta(minutes=30),
        )
        with self.assertRaises(LifecycleError):
            state.extend_fallback(
                registered + timedelta(minutes=121),
                now=registered + timedelta(minutes=31),
            )
        with self.assertRaises(LifecycleError):
            state.extend_fallback(
                registered + timedelta(minutes=120),
                now=registered + timedelta(minutes=119, seconds=1),
            )

    def test_remote_state_round_trip_rejects_digest_drift(self) -> None:
        config = configuration()
        state = LifecycleState(config.source_sha, sha256_json(config.to_dict()))
        state.transition(Phase.PREFLIGHTED)
        remote = state.to_dict(config)
        restored_config, restored_state = LifecycleState.from_dict(remote)
        self.assertEqual(restored_config, config)
        self.assertEqual(restored_state.phase, Phase.PREFLIGHTED)
        remote["configuration"]["environment"] = "monthly"  # type: ignore[index]
        with self.assertRaises(LifecycleError):
            LifecycleState.from_dict(remote)

    def test_remote_state_rejects_malformed_phase_and_failure(self) -> None:
        config = configuration()
        state = LifecycleState(config.source_sha, sha256_json(config.to_dict()))
        remote = state.to_dict(config)
        remote["phase"] = "invented"
        with self.assertRaises(LifecycleError):
            LifecycleState.from_dict(remote)
        remote = state.to_dict(config)
        remote["phase"] = "failed"
        remote["lastFailure"] = None
        with self.assertRaises(LifecycleError):
            LifecycleState.from_dict(remote)

    def test_image_identity_requires_all_three_digests(self) -> None:
        config = configuration()
        state = LifecycleState(config.source_sha, sha256_json(config.to_dict()))
        with self.assertRaises(LifecycleError):
            state.set_images({"web": "sha256:" + "1" * 64})
        state.set_images(
            {
                "web": "sha256:" + "1" * 64,
                "api": "sha256:" + "2" * 64,
                "ml": "sha256:" + "3" * 64,
            }
        )
        self.assertEqual(len(state.images), 3)

    def test_publish_retry_adopts_complete_immutable_image_effect(self) -> None:
        config = configuration()
        state = state_at(config, Phase.PREFLIGHTED)
        digests = {
            "web": "sha256:" + "1" * 64,
            "api": "sha256:" + "2" * 64,
            "ml": "sha256:" + "3" * 64,
        }
        operator = ImageInventoryAws(digests)
        source = FakeAws("arn:aws:iam::111122223333:user/ReactorFrontNoel")
        with (
            patch.object(lifecycle, "assume_role", return_value=operator),
            patch.object(lifecycle, "run_resume_preflight", return_value=operator),
            patch.object(lifecycle, "read_remote_state", return_value=(state, "etag")),
            patch.object(
                lifecycle, "write_remote_state", return_value="next-etag"
            ) as write,
        ):
            result = lifecycle.command_publish_images(
                config, Path("config.json"), source
            )
        self.assertEqual(result["imagePublication"], "reused")
        self.assertEqual(state.phase, Phase.IMAGES_PUBLISHED)
        self.assertEqual(state.images, digests)
        self.assertEqual(write.call_count, 1)
        self.assertFalse(
            any(
                service == "codebuild" and operation == "start-build"
                for service, operation, _arguments in operator.calls
            )
        )

    def test_publish_retry_rejects_partial_immutable_image_effect(self) -> None:
        config = configuration()
        state = state_at(config, Phase.PREFLIGHTED)
        operator = ImageInventoryAws({"web": "sha256:" + "1" * 64})
        source = FakeAws("arn:aws:iam::111122223333:user/ReactorFrontNoel")
        with (
            patch.object(lifecycle, "assume_role", return_value=operator),
            patch.object(lifecycle, "run_resume_preflight", return_value=operator),
            patch.object(lifecycle, "read_remote_state", return_value=(state, "etag")),
            patch.object(lifecycle, "write_remote_state", return_value="failed-etag"),
        ):
            with self.assertRaisesRegex(LifecycleError, "publication is partial"):
                lifecycle.command_publish_images(config, Path("config.json"), source)
        self.assertEqual(state.phase, Phase.FAILED)
        self.assertFalse(
            any(
                service == "codebuild" and operation == "start-build"
                for service, operation, _arguments in operator.calls
            )
        )

    def test_immutable_image_inventory_rejects_foreign_source_tag(self) -> None:
        config = configuration()
        operator = ImageInventoryAws(
            {
                "web": "sha256:" + "1" * 64,
                "api": "sha256:" + "2" * 64,
                "ml": "sha256:" + "3" * 64,
            },
            image_tag_override="sha-foreign",
        )
        with self.assertRaisesRegex(LifecycleError, "bind the exact source"):
            lifecycle.read_exact_image_digests(operator, config)

    def test_fresh_publication_starts_one_build_and_reads_back_digests(self) -> None:
        config = configuration()
        state = state_at(config, Phase.PREFLIGHTED)
        digests = {
            "web": "sha256:" + "1" * 64,
            "api": "sha256:" + "2" * 64,
            "ml": "sha256:" + "3" * 64,
        }
        operator = ImageInventoryAws({})
        source = FakeAws("arn:aws:iam::111122223333:user/ReactorFrontNoel")

        def finish_build(_client: object, _build_id: str) -> dict[str, object]:
            operator.images = digests
            return {
                "exportedEnvironmentVariables": [
                    {"name": f"{purpose.upper()}_DIGEST", "value": digest}
                    for purpose, digest in digests.items()
                ]
            }

        original_call = operator.call

        def call_with_build(
            service: str, operation: str, *arguments: str, **kwargs: object
        ):
            if service == "codebuild" and operation == "start-build":
                operator.calls.append((service, operation, arguments))
                return {"build": {"id": "exact-build"}}
            return original_call(service, operation, *arguments, **kwargs)

        operator.call = call_with_build  # type: ignore[method-assign]
        with (
            patch.object(lifecycle, "assume_role", return_value=operator),
            patch.object(lifecycle, "run_resume_preflight", return_value=operator),
            patch.object(lifecycle, "read_remote_state", return_value=(state, "etag")),
            patch.object(lifecycle, "wait_for_build", side_effect=finish_build),
            patch.object(lifecycle, "write_remote_state", return_value="next-etag"),
        ):
            result = lifecycle.command_publish_images(
                config, Path("config.json"), source
            )
        self.assertEqual(result["imagePublication"], "built")
        self.assertEqual(
            sum(
                service == "codebuild" and operation == "start-build"
                for service, operation, _arguments in operator.calls
            ),
            1,
        )

    def test_schedule_retry_adopts_effect_before_checkpoint(self) -> None:
        config = configuration()
        registered = lifecycle.utc_now()
        expiry = registered + timedelta(minutes=60)
        operator = ScheduleAws(registered)
        self.assertEqual(lifecycle.ensure_schedule(operator, config, expiry), "created")
        self.assertEqual(lifecycle.ensure_schedule(operator, config, expiry), "reused")
        creates = [
            call
            for call in operator.calls
            if call[0] == "scheduler" and call[1] == "create-schedule"
        ]
        self.assertEqual(len(creates), 1)

    def test_schedule_retry_rejects_mismatched_existing_effect(self) -> None:
        config = configuration()
        registered = lifecycle.utc_now()
        expiry = registered + timedelta(minutes=60)
        operator = ScheduleAws(registered)
        self.assertEqual(lifecycle.ensure_schedule(operator, config, expiry), "created")
        assert operator.schedule is not None
        target = dict(operator.schedule["Target"])  # type: ignore[arg-type]
        target["Arn"] = "arn:aws:codebuild:us-east-1:111122223333:project/foreign"
        operator.schedule["Target"] = target
        with self.assertRaisesRegex(LifecycleError, "read-back drifted"):
            lifecycle.ensure_schedule(operator, config, expiry)
        self.assertEqual(
            sum(
                service == "scheduler" and operation == "create-schedule"
                for service, operation, _arguments in operator.calls
            ),
            1,
        )

    def test_fallback_intent_is_checkpointed_before_schedule_creation(self) -> None:
        config = configuration()
        state = state_at(config, Phase.IMAGES_PUBLISHED)
        state.set_images(
            {
                "web": "sha256:" + "1" * 64,
                "api": "sha256:" + "2" * 64,
                "ml": "sha256:" + "3" * 64,
            }
        )
        registered = datetime(2026, 8, 11, 0, 0, tzinfo=UTC)
        operator = ScheduleAws(registered)
        source = FakeAws()
        snapshots: list[dict[str, object]] = []

        def record_state(
            _client: object,
            _config: object,
            _path: object,
            current: LifecycleState,
            **_kwargs: object,
        ) -> str:
            snapshots.append(current.to_dict(config))
            return f"etag-{len(snapshots)}"

        with (
            patch.object(lifecycle, "verify_source"),
            patch.object(lifecycle, "assume_role", return_value=operator),
            patch.object(lifecycle, "verify_controller") as verify_controller,
            patch.object(lifecycle, "read_remote_state", return_value=(state, "etag")),
            patch.object(
                lifecycle,
                "create_plan",
                return_value={
                    "fresh": True,
                    "counts": {},
                    "createdAt": lifecycle.isoformat(registered),
                },
            ),
            patch.object(lifecycle, "write_remote_state", side_effect=record_state),
            patch.object(lifecycle, "utc_now", return_value=registered),
        ):
            lifecycle.command_register_fallback(config, Path("config.json"), source, 60)
        first_state = snapshots[0]
        self.assertEqual(first_state["phase"], Phase.IMAGES_PUBLISHED.value)
        self.assertIn("fallbackIntent", first_state["checkpoints"])
        self.assertEqual(snapshots[-1]["phase"], Phase.FALLBACK_REGISTERED.value)
        self.assertNotIn("fallbackIntent", snapshots[-1]["checkpoints"])
        verify_controller.assert_called_once_with(
            config, operator, reconcile_image_buildspec=False
        )

    def test_register_fallback_adopts_existing_effect_without_intent(self) -> None:
        config = configuration()
        state = state_at(config, Phase.IMAGES_PUBLISHED)
        state.set_images(
            {
                "web": "sha256:" + "1" * 64,
                "api": "sha256:" + "2" * 64,
                "ml": "sha256:" + "3" * 64,
            }
        )
        registered = datetime(2026, 8, 11, 0, 0, tzinfo=UTC)
        expiry = registered + timedelta(minutes=60)
        operator = ScheduleAws(registered)
        with patch.object(lifecycle, "utc_now", return_value=registered):
            lifecycle.ensure_schedule(operator, config, expiry)
        operator.calls.clear()
        source = FakeAws()
        with (
            patch.object(lifecycle, "verify_source"),
            patch.object(lifecycle, "assume_role", return_value=operator),
            patch.object(lifecycle, "verify_controller"),
            patch.object(lifecycle, "read_remote_state", return_value=(state, "etag")),
            patch.object(
                lifecycle,
                "create_plan",
                return_value={
                    "fresh": True,
                    "counts": {},
                    "createdAt": lifecycle.isoformat(registered),
                },
            ),
            patch.object(lifecycle, "write_remote_state", return_value="next-etag"),
            patch.object(lifecycle, "utc_now", return_value=registered),
        ):
            result = lifecycle.command_register_fallback(
                config, Path("config.json"), source, 60
            )
        self.assertEqual(result["fallbackRegistration"], "reused")
        self.assertFalse(
            any(
                service == "scheduler" and operation == "create-schedule"
                for service, operation, _arguments in operator.calls
            )
        )

    def test_status_uses_complete_schedule_invariant_without_mutation(self) -> None:
        config = configuration()
        registered = datetime(2026, 8, 11, 0, 0, tzinfo=UTC)
        expiry = registered + timedelta(minutes=60)
        state = state_at(config, Phase.FALLBACK_REGISTERED)
        state.set_fallback(
            schedule_name=config.schedule_name,
            registered_at=registered,
            expires_at=expiry,
        )
        source = FakeAws()
        cases = ("canonical", "missing", "expired", *SCHEDULE_DRIFT_CASES)
        for case in cases:
            with self.subTest(case=case):
                operator = ScheduleAws(registered)
                lifecycle.ensure_schedule(operator, config, expiry)
                assert operator.schedule is not None
                if case == "missing":
                    operator.schedule = None
                elif case in SCHEDULE_DRIFT_CASES:
                    drift_schedule(operator.schedule, case, expiry)
                operator.calls.clear()
                instant = (
                    expiry + timedelta(seconds=1)
                    if case == "expired"
                    else registered + timedelta(minutes=10)
                )
                with (
                    patch.object(lifecycle, "verify_source"),
                    patch.object(lifecycle, "assume_role", return_value=operator),
                    patch.object(
                        lifecycle, "read_remote_state", return_value=(state, "etag")
                    ),
                    patch.object(
                        lifecycle,
                        "application_resources_possible",
                        return_value=False,
                    ),
                    patch.object(
                        lifecycle,
                        "utc_now",
                        return_value=instant,
                    ),
                ):
                    result = lifecycle.command_status(
                        config, Path("config.json"), source
                    )
                expected = (
                    "verified"
                    if case == "canonical"
                    else (
                        "expired-or-missing"
                        if case in {"missing", "expired"}
                        else "drifted"
                    )
                )
                self.assertEqual(result["fallback"], expected)
                self.assertFalse(
                    any(
                        service == "scheduler"
                        and operation in {"create-schedule", "update-schedule"}
                        for service, operation, _arguments in operator.calls
                    )
                )

    def test_extend_rejects_drift_before_any_write(self) -> None:
        config = configuration()
        registered = datetime(2026, 8, 11, 0, 0, tzinfo=UTC)
        expiry = registered + timedelta(minutes=60)
        cases = ("missing", "expired", *SCHEDULE_DRIFT_CASES)
        for case in cases:
            with self.subTest(case=case):
                state = state_at(config, Phase.FALLBACK_REGISTERED)
                state.set_fallback(
                    schedule_name=config.schedule_name,
                    registered_at=registered,
                    expires_at=expiry,
                )
                operator = ScheduleAws(registered)
                lifecycle.ensure_schedule(operator, config, expiry)
                assert operator.schedule is not None
                if case == "missing":
                    operator.schedule = None
                elif case in SCHEDULE_DRIFT_CASES:
                    drift_schedule(operator.schedule, case, expiry)
                operator.calls.clear()
                instant = (
                    expiry + timedelta(seconds=1)
                    if case == "expired"
                    else registered + timedelta(minutes=10)
                )
                with (
                    patch.object(lifecycle, "verify_source"),
                    patch.object(lifecycle, "assume_role", return_value=operator),
                    patch.object(
                        lifecycle,
                        "read_remote_state",
                        return_value=(state, "etag"),
                    ),
                    patch.object(lifecycle, "write_remote_state") as write,
                    patch.object(lifecycle, "utc_now", return_value=instant),
                ):
                    with self.assertRaises(LifecycleError):
                        lifecycle.command_extend(
                            config, Path("config.json"), FakeAws(), 20
                        )
                self.assertEqual(write.call_count, 0)
                self.assertNotIn("fallbackExtendIntent", state.checkpoints)
                self.assertFalse(
                    any(
                        service == "scheduler" and operation == "update-schedule"
                        for service, operation, _arguments in operator.calls
                    )
                )

    def test_extend_adopts_effect_before_final_checkpoint(self) -> None:
        config = configuration()
        registered = datetime(2026, 8, 11, 0, 0, tzinfo=UTC)
        expiry = registered + timedelta(minutes=60)
        state = state_at(config, Phase.FALLBACK_REGISTERED)
        state.set_fallback(
            schedule_name=config.schedule_name,
            registered_at=registered,
            expires_at=expiry,
        )
        operator = ScheduleAws(registered)
        lifecycle.ensure_schedule(operator, config, expiry)
        operator.calls.clear()
        source = FakeAws()
        snapshots: list[dict[str, object]] = []

        def interrupt_after_schedule(
            _client: object,
            _config: object,
            _path: object,
            current: LifecycleState,
            **_kwargs: object,
        ) -> str:
            snapshots.append(current.to_dict(config))
            if len(snapshots) == 1:
                return "intent-etag"
            raise LifecycleError("synthetic post-update interruption")

        with (
            patch.object(lifecycle, "verify_source"),
            patch.object(lifecycle, "assume_role", return_value=operator),
            patch.object(lifecycle, "read_remote_state", return_value=(state, "etag")),
            patch.object(
                lifecycle, "write_remote_state", side_effect=interrupt_after_schedule
            ),
            patch.object(
                lifecycle,
                "utc_now",
                return_value=registered + timedelta(minutes=10),
            ),
        ):
            with self.assertRaisesRegex(LifecycleError, "post-update interruption"):
                lifecycle.command_extend(config, Path("config.json"), source, 20)
        interrupted = LifecycleState.from_dict(snapshots[0])[1]
        self.assertIn("fallbackExtendIntent", interrupted.checkpoints)
        self.assertEqual(
            sum(
                service == "scheduler" and operation == "update-schedule"
                for service, operation, _arguments in operator.calls
            ),
            1,
        )
        with (
            patch.object(lifecycle, "verify_source"),
            patch.object(lifecycle, "assume_role", return_value=operator),
            patch.object(
                lifecycle,
                "read_remote_state",
                return_value=(interrupted, "intent-etag"),
            ),
            patch.object(lifecycle, "write_remote_state", return_value="final-etag"),
            patch.object(
                lifecycle,
                "utc_now",
                return_value=registered + timedelta(minutes=11),
            ),
        ):
            result = lifecycle.command_extend(config, Path("config.json"), source, 20)
        self.assertEqual(result["fallback"], "extended-and-verified")
        self.assertNotIn("fallbackExtendIntent", interrupted.checkpoints)
        self.assertEqual(
            sum(
                service == "scheduler" and operation == "update-schedule"
                for service, operation, _arguments in operator.calls
            ),
            1,
        )

    def test_migration_retry_reuses_idempotent_task_after_effect_gap(self) -> None:
        config = configuration()
        state = state_at(config, Phase.APPLIED)
        operator = MigrationAws(config)
        source = FakeAws()
        now = datetime(2026, 8, 11, 0, 0, tzinfo=UTC)
        snapshots: list[dict[str, object]] = []

        def interrupt_before_task_checkpoint(
            _client: object,
            _config: object,
            _path: object,
            current: LifecycleState,
            **_kwargs: object,
        ) -> str:
            snapshots.append(current.to_dict(config))
            if len(snapshots) == 1:
                return "intent-etag"
            raise LifecycleError("synthetic post-RunTask interruption")

        with (
            patch.object(lifecycle, "verify_source"),
            patch.object(lifecycle, "assume_role", return_value=operator),
            patch.object(lifecycle, "read_remote_state", return_value=(state, "etag")),
            patch.object(
                lifecycle, "terraform_output", return_value=migration_outputs(config)
            ),
            patch.object(
                lifecycle,
                "write_remote_state",
                side_effect=interrupt_before_task_checkpoint,
            ),
            patch.object(lifecycle, "utc_now", return_value=now),
        ):
            with self.assertRaisesRegex(LifecycleError, "post-RunTask interruption"):
                lifecycle.command_migrate(config, Path("config.json"), source)
        interrupted = LifecycleState.from_dict(snapshots[0])[1]
        self.assertEqual(interrupted.checkpoints["migration"], "running")
        self.assertIn("migrationIntent", interrupted.checkpoints)
        self.assertNotIn("migrationTaskArn", interrupted.checkpoints)
        with (
            patch.object(lifecycle, "verify_source"),
            patch.object(lifecycle, "assume_role", return_value=operator),
            patch.object(
                lifecycle,
                "read_remote_state",
                return_value=(interrupted, "intent-etag"),
            ),
            patch.object(
                lifecycle, "terraform_output", return_value=migration_outputs(config)
            ),
            patch.object(lifecycle, "write_remote_state", return_value="next-etag"),
            patch.object(lifecycle, "utc_now", return_value=now + timedelta(minutes=1)),
        ):
            result = lifecycle.command_migrate(config, Path("config.json"), source)
        self.assertEqual(result["migration"], "passed")
        self.assertEqual(operator.created_task_count, 1)
        self.assertEqual(
            sum(
                service == "ecs" and operation == "run-task"
                for service, operation, _arguments in operator.calls
            ),
            2,
        )
        self.assertEqual(interrupted.phase, Phase.MIGRATED)
        self.assertNotIn("migrationIntent", interrupted.checkpoints)
        self.assertNotIn("migrationTaskArn", interrupted.checkpoints)

    def test_migration_rejects_foreign_task_read_back(self) -> None:
        config = configuration()
        state = state_at(config, Phase.APPLIED)
        operator = MigrationAws(
            config,
            described_task_definition=(
                f"arn:{config.partition}:ecs:{config.region}:{config.account_id}:"
                "task-definition/foreign:1"
            ),
        )
        source = FakeAws()
        with (
            patch.object(lifecycle, "verify_source"),
            patch.object(lifecycle, "assume_role", return_value=operator),
            patch.object(lifecycle, "read_remote_state", return_value=(state, "etag")),
            patch.object(
                lifecycle, "terraform_output", return_value=migration_outputs(config)
            ),
            patch.object(lifecycle, "write_remote_state", return_value="next-etag"),
            patch.object(
                lifecycle,
                "utc_now",
                return_value=datetime(2026, 8, 11, 0, 0, tzinfo=UTC),
            ),
        ):
            with self.assertRaisesRegex(LifecycleError, "read-back drifted"):
                lifecycle.command_migrate(config, Path("config.json"), source)
        self.assertEqual(operator.created_task_count, 1)
        self.assertEqual(state.phase, Phase.FAILED)
        self.assertEqual(state.checkpoints["migration"], "unknown")

    def test_migration_retry_rejects_request_parameter_drift(self) -> None:
        config = configuration()
        state = state_at(config, Phase.APPLIED)
        outputs = migration_outputs(config)
        services = outputs["service_identifiers"]["value"]  # type: ignore[index]
        network = outputs["migration_network"]["value"]  # type: ignore[index]
        network_configuration = lifecycle.canonical_json(
            {
                "awsvpcConfiguration": {
                    "subnets": network["subnet_ids"],  # type: ignore[index]
                    "securityGroups": [network["security_group_id"]],  # type: ignore[index]
                    "assignPublicIp": "ENABLED",
                }
            }
        )
        tags = [
            {"key": key, "value": value} for key, value in config.ownership_tags.items()
        ]
        now = datetime(2026, 8, 11, 0, 0, tzinfo=UTC)
        intent = lifecycle.expected_migration_intent(
            state,
            services,  # type: ignore[arg-type]
            network_configuration,
            tags,
            attempt=1,
            requested_at=now,
        )
        state.transition(
            Phase.APPLIED,
            checkpoint={"migration": "running", "migrationIntent": intent},
        )
        drifted_outputs = migration_outputs(config)
        drifted_outputs["migration_network"]["value"]["subnet_ids"] = [  # type: ignore[index]
            "subnet-foreign"
        ]
        operator = MigrationAws(config)
        with (
            patch.object(lifecycle, "verify_source"),
            patch.object(lifecycle, "assume_role", return_value=operator),
            patch.object(lifecycle, "read_remote_state", return_value=(state, "etag")),
            patch.object(lifecycle, "terraform_output", return_value=drifted_outputs),
        ):
            with self.assertRaisesRegex(LifecycleError, "foreign or drifted"):
                lifecycle.command_migrate(config, Path("config.json"), FakeAws())
        self.assertFalse(
            any(
                service == "ecs" and operation == "run-task"
                for service, operation, _arguments in operator.calls
            )
        )

    def test_parallel_seed_claim_rejects_stale_owner_before_external_effects(
        self,
    ) -> None:
        config = configuration()
        remote = SeedRemote(config)
        stale_state, stale_etag = remote.read()
        cloud = SeedCloud()
        outputs = {
            "service_identifiers": {"value": {"cognito_user_pool_id": "synthetic-pool"}}
        }

        def write_remote(
            _client: object,
            _config: object,
            _path: object,
            current: LifecycleState,
            **kwargs: object,
        ) -> str:
            return remote.write(current, kwargs.get("if_match"))  # type: ignore[arg-type]

        def put_secret(
            client: SeedAws,
            _config: object,
            _key: object,
            payload: dict[str, object],
            _path: object,
            **kwargs: object,
        ) -> str:
            if kwargs.get("if_none_match") and client.cloud.secret is not None:
                raise LifecycleError("Synthetic secret already exists.")
            client.cloud.secret = dict(payload)
            return "secret-etag"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_path = root / "first" / "config.json"
            second_path = root / "second" / "config.json"
            first = SeedAws(cloud)
            with (
                patch.object(lifecycle, "verify_source"),
                patch.object(lifecycle, "assume_role", return_value=first),
                patch.object(
                    lifecycle,
                    "read_remote_state",
                    side_effect=lambda *_args, **_kwargs: remote.read(),
                ),
                patch.object(lifecycle, "write_remote_state", side_effect=write_remote),
                patch.object(lifecycle, "terraform_output", return_value=outputs),
                patch.object(lifecycle, "s3_put_json", side_effect=put_secret),
                patch.object(
                    lifecycle, "generated_password", return_value="password-A"
                ),
            ):
                result = lifecycle.command_seed(config, first_path, FakeAws())
            self.assertEqual(result["phase"], Phase.SEEDED.value)

            second = SeedAws(cloud)
            with (
                patch.object(lifecycle, "verify_source"),
                patch.object(lifecycle, "assume_role", return_value=second),
                patch.object(
                    lifecycle,
                    "read_remote_state",
                    return_value=(stale_state, stale_etag),
                ),
                patch.object(lifecycle, "write_remote_state", side_effect=write_remote),
                patch.object(lifecycle, "terraform_output", return_value=outputs),
                patch.object(lifecycle, "s3_put_json", side_effect=put_secret),
                patch.object(
                    lifecycle, "generated_password", return_value="password-B"
                ),
            ):
                with self.assertRaisesRegex(LifecycleError, "stale lifecycle ETag"):
                    lifecycle.command_seed(config, second_path, FakeAws())

        self.assertFalse(
            any(
                service in {"cognito-idp", "s3api"}
                and operation
                in {
                    "admin-delete-user",
                    "admin-create-user",
                    "admin-set-user-password",
                    "admin-add-user-to-group",
                    "delete-object",
                }
                for service, operation, _arguments in second.calls
            )
        )
        final = LifecycleState.from_dict(remote.payload)[1]
        self.assertEqual(final.phase, Phase.SEEDED)
        self.assertEqual(final.checkpoints["seed"], "passed")
        self.assertNotIn("seedIntent", final.checkpoints)
        self.assertIsNotNone(cloud.secret)
        self.assertEqual(cloud.password, cloud.secret["password"])  # type: ignore[index]

    def test_seed_exact_owner_recovers_but_foreign_checkout_fails_closed(self) -> None:
        config = configuration()
        remote = SeedRemote(config)
        cloud = SeedCloud()
        outputs = {
            "service_identifiers": {"value": {"cognito_user_pool_id": "synthetic-pool"}}
        }

        def write_remote(
            _client: object,
            _config: object,
            _path: object,
            current: LifecycleState,
            **kwargs: object,
        ) -> str:
            return remote.write(current, kwargs.get("if_match"))  # type: ignore[arg-type]

        def put_secret(
            client: SeedAws,
            _config: object,
            _key: object,
            payload: dict[str, object],
            _path: object,
            **_kwargs: object,
        ) -> str:
            client.cloud.secret = dict(payload)
            return "secret-etag"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            owner_path = root / "owner" / "config.json"
            foreign_path = root / "foreign" / "config.json"
            interrupted = SeedAws(cloud)
            with (
                patch.object(lifecycle, "verify_source"),
                patch.object(lifecycle, "assume_role", return_value=interrupted),
                patch.object(
                    lifecycle,
                    "read_remote_state",
                    side_effect=lambda *_args, **_kwargs: remote.read(),
                ),
                patch.object(lifecycle, "write_remote_state", side_effect=write_remote),
                patch.object(
                    lifecycle,
                    "terraform_output",
                    side_effect=LifecycleError("synthetic post-claim interruption"),
                ),
            ):
                with self.assertRaisesRegex(LifecycleError, "post-claim interruption"):
                    lifecycle.command_seed(config, owner_path, FakeAws())
            claimed = LifecycleState.from_dict(remote.payload)[1]
            self.assertEqual(claimed.phase, Phase.MIGRATED)
            self.assertEqual(claimed.checkpoints["seed"], "running")
            self.assertIn("seedIntent", claimed.checkpoints)

            foreign = SeedAws(cloud)
            with (
                patch.object(lifecycle, "verify_source"),
                patch.object(lifecycle, "assume_role", return_value=foreign),
                patch.object(
                    lifecycle,
                    "read_remote_state",
                    side_effect=lambda *_args, **_kwargs: remote.read(),
                ),
                patch.object(lifecycle, "write_remote_state", side_effect=write_remote),
            ):
                with self.assertRaisesRegex(
                    LifecycleError, "exact local recovery identity is unavailable"
                ):
                    lifecycle.command_seed(config, foreign_path, FakeAws())
            self.assertFalse(
                any(
                    service in {"cognito-idp", "s3api"}
                    for service, _, _ in foreign.calls
                )
            )

            resumed = SeedAws(cloud)
            with (
                patch.object(lifecycle, "verify_source"),
                patch.object(lifecycle, "assume_role", return_value=resumed),
                patch.object(
                    lifecycle,
                    "read_remote_state",
                    side_effect=lambda *_args, **_kwargs: remote.read(),
                ),
                patch.object(lifecycle, "write_remote_state", side_effect=write_remote),
                patch.object(lifecycle, "terraform_output", return_value=outputs),
                patch.object(lifecycle, "s3_put_json", side_effect=put_secret),
                patch.object(
                    lifecycle, "generated_password", return_value="recovered-password"
                ),
            ):
                result = lifecycle.command_seed(config, owner_path, FakeAws())
            self.assertEqual(result["phase"], Phase.SEEDED.value)
            self.assertFalse(lifecycle.seed_recovery_path(owner_path).exists())

        final = LifecycleState.from_dict(remote.payload)[1]
        self.assertEqual(final.phase, Phase.SEEDED)
        self.assertEqual(final.checkpoints["seed"], "passed")
        self.assertNotIn("seedIntent", final.checkpoints)
        self.assertIsNotNone(cloud.secret)
        self.assertEqual(cloud.password, cloud.secret["password"])  # type: ignore[index]

    def test_seed_local_lock_rejects_a_second_process_before_remote_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            with lifecycle.seed_operation_lock(config_path):
                with self.assertRaisesRegex(
                    LifecycleError, "Another local seed invocation"
                ):
                    with lifecycle.seed_operation_lock(config_path):
                        self.fail("A second local seed process acquired the lock.")

    def test_smoke_process_failure_records_running_then_failed(self) -> None:
        config = configuration()
        outputs = {
            "public_endpoints": {
                "value": {
                    "web_https": "https://example.execute-api.us-east-1.amazonaws.com"
                }
            }
        }
        failures = {
            "process": LifecycleError("synthetic Playwright failure"),
            "timeout": lifecycle.subprocess.TimeoutExpired("pnpm", 600),
        }
        for label, failure in failures.items():
            with self.subTest(label=label):
                state = state_at(config, Phase.SEEDED)
                operator = FakeAws()
                source = FakeAws()
                snapshots: list[dict[str, object]] = []

                def record_state(
                    _client: object,
                    _config: object,
                    _path: object,
                    current: LifecycleState,
                    **_kwargs: object,
                ) -> str:
                    snapshots.append(current.to_dict(config))
                    return f"etag-{len(snapshots)}"

                with tempfile.TemporaryDirectory() as directory:
                    config_path = Path(directory) / "configuration.json"
                    with (
                        patch.object(lifecycle, "verify_source"),
                        patch.object(lifecycle, "assume_role", return_value=operator),
                        patch.object(
                            lifecycle,
                            "read_remote_state",
                            return_value=(state, "etag"),
                        ),
                        patch.object(
                            lifecycle, "terraform_output", return_value=outputs
                        ),
                        patch.object(
                            lifecycle,
                            "s3_get_json",
                            return_value=(
                                {"username": "synthetic", "password": "private"},
                                "etag",
                            ),
                        ),
                        patch.object(lifecycle, "require_command", return_value="pnpm"),
                        patch.object(lifecycle, "run_process", side_effect=failure),
                        patch.object(
                            lifecycle,
                            "write_remote_state",
                            side_effect=record_state,
                        ),
                    ):
                        with self.assertRaises(type(failure)):
                            lifecycle.command_smoke(config, config_path, source)
                self.assertEqual(len(snapshots), 2)
                running = LifecycleState.from_dict(snapshots[0])[1]
                failed = LifecycleState.from_dict(snapshots[1])[1]
                self.assertEqual(running.phase, Phase.SEEDED)
                self.assertEqual(running.checkpoints["smoke"], "running")
                self.assertEqual(failed.phase, Phase.FAILED)
                self.assertEqual(
                    failed.last_failure["operation"],
                    "smoke",  # type: ignore[index]
                )
                self.assertEqual(sanitized_status(failed)["smoke"], "failed")

    def test_smoke_preserves_cause_when_failure_checkpoint_also_fails(self) -> None:
        config = configuration()
        state = state_at(config, Phase.SEEDED)
        operator = FakeAws()
        causal_error = LifecycleError("synthetic causal Playwright failure")
        checkpoint_error = LifecycleError("synthetic checkpoint failure")
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "configuration.json"
            with (
                patch.object(lifecycle, "verify_source"),
                patch.object(lifecycle, "assume_role", return_value=operator),
                patch.object(
                    lifecycle, "read_remote_state", return_value=(state, "etag")
                ),
                patch.object(
                    lifecycle,
                    "terraform_output",
                    return_value={
                        "public_endpoints": {
                            "value": {
                                "web_https": "https://example.execute-api.us-east-1.amazonaws.com"
                            }
                        }
                    },
                ),
                patch.object(
                    lifecycle,
                    "s3_get_json",
                    return_value=(
                        {"username": "synthetic", "password": "private"},
                        "etag",
                    ),
                ),
                patch.object(lifecycle, "require_command", return_value="pnpm"),
                patch.object(lifecycle, "run_process", side_effect=causal_error),
                patch.object(
                    lifecycle,
                    "write_remote_state",
                    side_effect=("running-etag", checkpoint_error),
                ),
            ):
                with self.assertRaisesRegex(
                    LifecycleError, "causal Playwright"
                ) as raised:
                    lifecycle.command_smoke(config, config_path, FakeAws())
        self.assertIs(raised.exception, causal_error)
        self.assertIs(raised.exception.__cause__, checkpoint_error)
        self.assertIn("checkpoint also failed safely", raised.exception.__notes__[0])

    def test_destroy_requires_a_remote_write_boundary(self) -> None:
        config = configuration()
        state = LifecycleState(config.source_sha, sha256_json(config.to_dict()))
        with self.assertRaises(LifecycleError):
            state.transition(Phase.DESTROYING)
        state.transition(Phase.PREFLIGHTED)
        state.transition(Phase.DESTROYING)
        self.assertEqual(state.phase, Phase.DESTROYING)

    def test_preapply_failure_skips_terraform_but_retains_cleanup(self) -> None:
        config = configuration()
        state = LifecycleState(config.source_sha, sha256_json(config.to_dict()))
        state.transition(Phase.PREFLIGHTED)
        state.record_failure("publish-images")
        self.assertFalse(lifecycle.application_resources_possible(state))
        state.resume(Phase.PREFLIGHTED)
        state.transition(Phase.IMAGES_PUBLISHED)
        state.transition(Phase.FALLBACK_REGISTERED)
        state.transition(Phase.APPLYING)
        self.assertTrue(lifecycle.application_resources_possible(state))

    def test_conditional_lease_and_etag_update_are_forwarded_exactly(self) -> None:
        config = configuration()
        fake = FakeAws()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "state.json"
            lifecycle.s3_put_json(
                fake,
                config,
                config.lease_key,
                {"phase": "leased"},
                source,
                if_none_match=True,
            )
            lifecycle.s3_put_json(
                fake,
                config,
                config.configuration_key,
                {"phase": "updated"},
                source,
                if_match="previous-etag",
            )
        put_arguments = [
            arguments
            for service, operation, arguments in fake.calls
            if service == "s3api" and operation == "put-object"
        ]
        self.assertIn(
            ("--if-none-match", "*"), tuple(zip(put_arguments[0], put_arguments[0][1:]))
        )
        self.assertIn(
            ("--if-match", "previous-etag"),
            tuple(zip(put_arguments[1], put_arguments[1][1:])),
        )

    def test_only_exact_source_lease_is_recoverable(self) -> None:
        config = configuration()
        lifecycle.validate_lease_payload(
            {
                "schemaVersion": 1,
                "deploymentId": config.source_sha,
                "acquiredAt": "2026-08-10T00:00:00Z",
            },
            config,
        )
        with self.assertRaises(LifecycleError):
            lifecycle.validate_lease_payload(
                {
                    "schemaVersion": 1,
                    "deploymentId": "2" * 40,
                    "acquiredAt": "2026-08-10T00:00:00Z",
                },
                config,
            )

    def test_wrong_source_identity_fails_before_assumption(self) -> None:
        with self.assertRaises(LifecycleError):
            lifecycle.verify_source(
                configuration(),
                FakeAws("arn:aws:iam::111122223333:user/unrelated"),
            )

    def test_controller_failure_is_checkpointed_for_automatic_retry(self) -> None:
        config = configuration()
        state = state_at(config, Phase.SMOKE_PASSED)
        controller = FakeAws(
            "arn:aws:sts::111122223333:assumed-role/"
            "reactorfront-manual-codebuild-destroy/build"
        )
        destroy = FakeAws()
        with (
            patch.object(lifecycle, "read_remote_state", return_value=(state, "etag")),
            patch.object(lifecycle, "assume_role", return_value=destroy),
            patch.object(
                lifecycle,
                "write_remote_state",
                side_effect=("next-etag", "failed-etag"),
            ) as write,
            patch.object(
                lifecycle,
                "terraform_destroy",
                side_effect=LifecycleError("synthetic destroy failure"),
            ),
        ):
            with self.assertRaises(LifecycleError):
                lifecycle.command_controller_destroy(
                    config, Path("config.json"), controller
                )
        self.assertEqual(state.phase, Phase.FAILED)
        self.assertEqual(state.last_failure["operation"], "controller-destroy")  # type: ignore[index]
        self.assertEqual(write.call_count, 2)

    def test_destroy_removes_only_three_exact_image_digests(self) -> None:
        config = configuration()
        state = LifecycleState(config.source_sha, sha256_json(config.to_dict()))
        state.set_images(
            {
                "web": "sha256:" + "1" * 64,
                "api": "sha256:" + "2" * 64,
                "ml": "sha256:" + "3" * 64,
            }
        )
        fake = FakeAws()
        lifecycle.cleanup_published_images(config, state, fake)
        deletes = [
            arguments
            for service, operation, arguments in fake.calls
            if service == "ecr" and operation == "batch-delete-image"
        ]
        self.assertEqual(len(deletes), 3)
        self.assertEqual(
            {arguments[1] for arguments in deletes},
            {"reactorfront/web", "reactorfront/api", "reactorfront/ml"},
        )

    def test_terraform_destroy_uses_state_then_independent_sweep(self) -> None:
        config = configuration()
        state = state_at(config, Phase.APPLYING)
        fake = FakeAws()
        with (
            patch.object(
                lifecycle,
                "terraform_init",
                return_value=(Path("environment"), Path("vars.json"), Path("plan")),
            ),
            patch.object(lifecycle, "require_command", return_value="terraform"),
            patch.object(lifecycle, "run_process") as run,
        ):
            run.return_value.stdout = "\n".join(
                (
                    "module.managed_state.aws_secretsmanager_secret_version.broker",
                    "module.managed_state.aws_secretsmanager_secret_version.database",
                    "module.network.aws_vpc.this",
                )
            )
            lifecycle.terraform_destroy(config, state, Path("config.json"), fake)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[0][-2:], ["state", "list"])
        self.assertEqual(
            [command[-2:] for command in commands[1:3]],
            [
                [
                    "rm",
                    "module.managed_state.aws_secretsmanager_secret_version.broker",
                ],
                [
                    "rm",
                    "module.managed_state.aws_secretsmanager_secret_version.database",
                ],
            ],
        )
        self.assertIn("-refresh=false", commands[-1])

    def test_terraform_destroy_skips_absent_secret_versions(self) -> None:
        config = configuration()
        state = state_at(config, Phase.APPLYING)
        fake = FakeAws()
        with (
            patch.object(
                lifecycle,
                "terraform_init",
                return_value=(Path("environment"), Path("vars.json"), Path("plan")),
            ),
            patch.object(lifecycle, "require_command", return_value="terraform"),
            patch.object(lifecycle, "run_process") as run,
        ):
            run.return_value.stdout = "module.network.aws_vpc.this\n"
            lifecycle.terraform_destroy(config, state, Path("config.json"), fake)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(len(commands), 2)
        self.assertEqual(commands[0][-2:], ["state", "list"])
        self.assertIn("destroy", commands[1])

    def test_control_cleanup_deletes_configuration_last(self) -> None:
        config = configuration()
        fake = FakeAws()
        lifecycle.cleanup_completed_controls(config, fake)
        deleted_keys = [
            arguments[arguments.index("--key") + 1]
            for service, operation, arguments in fake.calls
            if service == "s3api" and operation == "delete-object"
        ]
        self.assertEqual(
            deleted_keys,
            [config.secret_key, config.lease_key, config.configuration_key],
        )
        schedule_delete = next(
            arguments
            for service, operation, arguments in fake.calls
            if service == "scheduler" and operation == "delete-schedule"
        )
        self.assertEqual(
            schedule_delete[schedule_delete.index("--group-name") + 1],
            config.schedule_group_name,
        )

    def test_tag_inventory_ignores_only_service_proved_ghosts(self) -> None:
        mappings = [
            {
                "ResourceARN": (
                    "arn:aws:cognito-idp:us-east-1:111122223333:"
                    "userpool/us-east-1_deleted"
                )
            },
            {
                "ResourceARN": (
                    "arn:aws:ecs:us-east-1:111122223333:"
                    "task-definition/reactorfront-manual-web:1"
                )
            },
            {
                "ResourceARN": (
                    "arn:aws:ecs:us-east-1:111122223333:"
                    "service/reactorfront-manual/reactorfront-manual-web"
                )
            },
            {
                "ResourceARN": (
                    "arn:aws:ecs:us-east-1:111122223333:"
                    "task/reactorfront-manual/deleted"
                )
            },
            {
                "ResourceARN": (
                    "arn:aws:ec2:us-east-1:111122223333:security-group-rule/sgr-deleted"
                )
            },
        ]
        inventory = {
            "cognitoUserPool": 0,
            "activeTaskDefinition": 0,
            "ecsService": 0,
            "ecsTask": 0,
            "securityGroup": 0,
        }
        self.assertEqual(
            lifecycle.unresolved_tagged_resource_count(mappings, inventory), 0
        )
        inventory["activeTaskDefinition"] = 1
        self.assertEqual(
            lifecycle.unresolved_tagged_resource_count(mappings, inventory), 1
        )

    def test_tag_inventory_keeps_unknown_kinds_fail_closed(self) -> None:
        mappings = [
            {"ResourceARN": ("arn:aws:unexpected:us-east-1:111122223333:thing/example")}
        ]
        self.assertEqual(lifecycle.unresolved_tagged_resource_count(mappings, {}), 1)

    def test_status_never_claims_missing_evidence(self) -> None:
        empty = sanitized_status(None)
        self.assertEqual(empty["phase"], "not-attempted")
        self.assertEqual(empty["residue"], "unknown")
        config = configuration()
        state = LifecycleState(config.source_sha, sha256_json(config.to_dict()))
        status = sanitized_status(state)
        self.assertEqual(status["smoke"], "not-attempted")
        self.assertEqual(status["fallback"], "missing")

    def test_public_output_rejects_credentials_account_and_private_paths(self) -> None:
        for unsafe in (
            {"accessKey": "redacted"},
            {"value": "111122223333"},
            {"value": "AKIA" + "ABCDEFGHIJKLMNOP"},
            {"value": "C:\\private\\context.json"},
        ):
            with self.assertRaises(LifecycleError):
                assert_public_safe(unsafe)
        assert_public_safe({"phase": "applied", "resourceCounts": {"created": 81}})
        assert_public_safe(
            {"sourceRevision": "27f4f755323807584dfcd2cd25625503df04b012"}
        )
        assert_public_safe({"imageDigest": "sha256:" + "7" * 64})

    def test_failed_process_retains_only_private_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            (repository / ".git").mkdir()
            with patch.object(lifecycle, "REPOSITORY_ROOT", repository):
                with self.assertRaises(LifecycleError) as raised:
                    lifecycle.run_process(
                        [
                            sys.executable,
                            "-c",
                            "import sys; print('private-value', file=sys.stderr); sys.exit(1)",
                        ],
                        label="Synthetic process",
                    )
            self.assertNotIn("private-value", str(raised.exception))
            diagnostic = (
                repository
                / ".git"
                / "portfolio-aws-lifecycle"
                / "private-diagnostics"
                / "synthetic-process.log"
            )
            self.assertIn("private-value", diagnostic.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
