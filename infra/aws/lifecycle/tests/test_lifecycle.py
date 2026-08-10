from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from aws_lifecycle_core import (  # noqa: E402
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


class LifecycleContractTests(unittest.TestCase):
    def test_configuration_round_trip_and_exact_bindings(self) -> None:
        expected = configuration()
        actual = LifecycleConfig.from_dict(expected.to_dict())
        self.assertEqual(actual, expected)
        self.assertEqual(
            actual.configuration_key, "controls/reactorfront/manual/configuration.json"
        )
        self.assertEqual(actual.schedule_name, "reactorfront-manual-destroy")
        self.assertEqual(actual.schedule_group_name, "reactorfront-manual-lifecycle")

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
            lifecycle.terraform_destroy(config, state, Path("config.json"), fake)
        command = run.call_args.args[0]
        self.assertIn("-refresh=false", command)

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
        ]
        inventory = {"cognitoUserPool": 0, "activeTaskDefinition": 0}
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
