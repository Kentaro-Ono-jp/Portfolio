from __future__ import annotations

import base64
import json
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from aws_automation_contract import (
    EXPECTED_IMMUTABLE_REPOSITORY_SUBJECT,
    expected_oidc_subject,
    validate_repository_subject,
)
from aws_automation_guard import (
    EXPECTED_ENVIRONMENT,
    EXPECTED_REF,
    EXPECTED_REPOSITORY,
    EXPECTED_WORKFLOW,
    PERMANENT_SCHEDULE,
    select_route,
)
from aws_automation_maintenance import (
    AwsCli,
    aws_error_code,
    build_contract,
    ensure_monthly_controllers,
    ensure_role,
    is_transient_aws_failure,
    lifecycle_config,
    ordered_role_specs,
)
from aws_oidc_claim_guard import (
    decode_claims,
    expected_claims,
    validate_claims,
)


@dataclass
class MaintenanceEffects:
    trusts_updated: int = 0


class DriftedRoleAws:
    def __init__(self, spec: dict[str, Any]) -> None:
        self.spec = spec
        self.effects = MaintenanceEffects()
        self.calls: list[tuple[str, str]] = []

    def call(
        self,
        service: str,
        operation: str,
        *arguments: str,
        **_: Any,
    ) -> dict[str, Any]:
        self.calls.append((service, operation))
        if operation == "get-role":
            return {
                "Role": {
                    "Path": "/",
                    "MaxSessionDuration": 3600,
                    "PermissionsBoundary": {
                        "PermissionsBoundaryArn": (
                            "arn:aws:iam::111122223333:policy/ExactBoundary"
                        )
                    },
                    "Tags": [
                        {"Key": key, "Value": value}
                        for key, value in self.spec["tags"].items()
                    ],
                    "AssumeRolePolicyDocument": {"Version": "2012-10-17"},
                }
            }
        if operation == "list-attached-role-policies":
            return {
                "AttachedPolicies": [
                    {"PolicyArn": ("arn:aws:iam::111122223333:policy/ExactPermission")},
                    {
                        "PolicyArn": (
                            "arn:aws:iam::111122223333:policy/UndeclaredPermission"
                        )
                    },
                ]
            }
        if operation == "list-role-policies":
            return {"PolicyNames": []}
        return {}


class MissingControllerAws:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def call(
        self,
        service: str,
        operation: str,
        *_: str,
        **__: Any,
    ) -> dict[str, Any] | None:
        self.calls.append((service, operation))
        if operation == "get-schedule-group":
            return None
        if operation == "describe-log-groups":
            return {"logGroups": []}
        if operation == "batch-get-projects":
            return {"projects": []}
        raise AssertionError(f"Unexpected read-only controller call: {operation}")


def context(**overrides: str) -> dict[str, str]:
    values = {
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REPOSITORY": EXPECTED_REPOSITORY,
        "GITHUB_REPOSITORY_OWNER": "Kentaro-Ono-jp",
        "GITHUB_ACTOR": "Kentaro-Ono-jp",
        "GITHUB_TRIGGERING_ACTOR": "Kentaro-Ono-jp",
        "GITHUB_REF": EXPECTED_REF,
        "GITHUB_WORKFLOW": EXPECTED_WORKFLOW,
        "GITHUB_SHA": "a" * 40,
        "GITHUB_EVENT_SCHEDULE": "",
        "PORTFOLIO_GITHUB_ENVIRONMENT": EXPECTED_ENVIRONMENT,
        "PORTFOLIO_PERMANENT_SCHEDULE": PERMANENT_SCHEDULE,
        "PORTFOLIO_TEMPORARY_SCHEDULE": "",
    }
    values.update(overrides)
    return values


class AutomationGuardTests(unittest.TestCase):
    def test_owner_dispatch_maps_only_to_manual(self) -> None:
        route = select_route(context())

        self.assertEqual(route.event_name, "workflow_dispatch")
        self.assertEqual(route.mode, "manual")
        self.assertEqual(route.schedule_kind, "not-scheduled")

    def test_permanent_schedule_maps_only_to_monthly(self) -> None:
        route = select_route(
            context(
                GITHUB_EVENT_NAME="schedule",
                GITHUB_EVENT_SCHEDULE=PERMANENT_SCHEDULE,
            )
        )

        self.assertEqual(route.event_name, "schedule")
        self.assertEqual(route.mode, "monthly")
        self.assertEqual(route.schedule_kind, "permanent")

    def test_recorded_temporary_schedule_maps_only_to_monthly(self) -> None:
        route = select_route(
            context(
                GITHUB_EVENT_NAME="schedule",
                GITHUB_EVENT_SCHEDULE="35 17 11 * *",
                PORTFOLIO_TEMPORARY_SCHEDULE="35 17 11 * *",
            )
        )

        self.assertEqual(route.mode, "monthly")
        self.assertEqual(route.schedule_kind, "temporary")

    def test_unrecorded_schedule_fails_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "not repository-owned"):
            select_route(
                context(
                    GITHUB_EVENT_NAME="schedule",
                    GITHUB_EVENT_SCHEDULE="5 4 * * *",
                )
            )

    def test_non_owner_dispatch_fails_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "repository owner"):
            select_route(context(GITHUB_ACTOR="someone-else"))
        with self.assertRaisesRegex(RuntimeError, "repository owner"):
            select_route(context(GITHUB_TRIGGERING_ACTOR="someone-else"))

    def test_wrong_source_boundaries_fail_closed(self) -> None:
        mutations = {
            "repository": {"GITHUB_REPOSITORY": "fork-owner/Portfolio"},
            "ref": {"GITHUB_REF": "refs/heads/feature"},
            "workflow": {"GITHUB_WORKFLOW": "Verify"},
            "environment": {"PORTFOLIO_GITHUB_ENVIRONMENT": "production"},
            "sha": {"GITHUB_SHA": "short"},
            "event": {"GITHUB_EVENT_NAME": "push"},
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label), self.assertRaises(RuntimeError):
                select_route(context(**mutation))

    def test_temporary_schedule_cannot_duplicate_permanent(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "must be distinct"):
            select_route(
                context(
                    GITHUB_EVENT_NAME="schedule",
                    GITHUB_EVENT_SCHEDULE=PERMANENT_SCHEDULE,
                    PORTFOLIO_TEMPORARY_SCHEDULE=PERMANENT_SCHEDULE,
                )
            )

    def test_monthly_maintenance_configuration_uses_the_schedule_caller(self) -> None:
        config = lifecycle_config(
            account_id="111122223333",
            partition="aws",
            region="us-east-1",
            name_prefix="reactorfront",
            repository=EXPECTED_REPOSITORY,
            state_bucket="reactorfront-111122223333-us-east-1-state",
        )

        self.assertEqual(config.environment, "monthly")
        self.assertEqual(config.caller_mode, "github-automation")
        self.assertEqual(config.caller_event, "schedule")

    def test_role_drift_is_fully_checked_before_trust_update(self) -> None:
        spec = {
            "name": "reactorfront-automation",
            "trust": {"Version": "2012-10-17", "Statement": []},
            "permissions": ["ExactPermission"],
            "boundary": "ExactBoundary",
            "tags": {
                "PortfolioEnvironment": "shared",
                "PortfolioManaged": "true",
                "PortfolioPersistent": "true",
                "PortfolioRepository": EXPECTED_REPOSITORY,
                "PortfolioPurpose": "automation",
            },
        }
        aws = DriftedRoleAws(spec)

        with self.assertRaisesRegex(RuntimeError, "undeclared policy"):
            ensure_role(
                aws,  # type: ignore[arg-type]
                apply=True,
                account_id="111122223333",
                partition="aws",
                spec=spec,
            )

        self.assertNotIn(("iam", "update-assume-role-policy"), aws.calls)
        self.assertEqual(aws.effects.trusts_updated, 0)

    def test_all_internal_trust_dependencies_drive_role_creation_order(self) -> None:
        _, roles = build_contract(
            "111122223333",
            "aws",
            "us-east-1",
            "reactorfront",
            EXPECTED_REPOSITORY,
            "reactorfront-111122223333-us-east-1-state",
            EXPECTED_IMMUTABLE_REPOSITORY_SUBJECT,
        )

        names = [
            str(spec["name"])
            for spec in ordered_role_specs(
                roles,
                account_id="111122223333",
                partition="aws",
            )
        ]

        self.assertEqual(names[0], "reactorfront-automation")
        automation_trust = roles["reactorfront-automation"]["trust"]
        subjects = automation_trust["Statement"][0]["Condition"]["StringEquals"][
            "token.actions.githubusercontent.com:sub"
        ]
        self.assertEqual(
            set(subjects),
            {
                expected_oidc_subject("workflow_dispatch"),
                expected_oidc_subject("schedule"),
            },
        )
        for environment in ("manual", "monthly"):
            destroy = names.index(f"reactorfront-{environment}-destroy")
            for dependency in (
                "automation",
                "operator-deployment",
                "codebuild-destroy",
                "scheduler",
            ):
                role_name = (
                    "reactorfront-automation"
                    if dependency == "automation"
                    else f"reactorfront-{environment}-{dependency}"
                )
                self.assertLess(names.index(role_name), destroy)

    def test_role_dependency_graph_rejects_cycles_and_undeclared_internal_roles(
        self,
    ) -> None:
        prefix = "arn:aws:iam::111122223333:role/"
        cyclic = {
            "reactorfront-a": {
                "name": "reactorfront-a",
                "trust": {
                    "Statement": [{"Principal": {"AWS": prefix + "reactorfront-b"}}]
                },
            },
            "reactorfront-b": {
                "name": "reactorfront-b",
                "trust": {
                    "Statement": [{"Principal": {"AWS": prefix + "reactorfront-a"}}]
                },
            },
        }
        with self.assertRaisesRegex(RuntimeError, "contains a cycle"):
            ordered_role_specs(
                cyclic,
                account_id="111122223333",
                partition="aws",
            )

        cyclic["reactorfront-b"]["trust"] = {
            "Statement": [{"Principal": {"AWS": prefix + "reactorfront-undeclared"}}]
        }
        with self.assertRaisesRegex(RuntimeError, "undeclared internal role"):
            ordered_role_specs(
                cyclic,
                account_id="111122223333",
                partition="aws",
            )

    def test_transient_aws_failures_are_classified_for_all_iam_writes(self) -> None:
        self.assertTrue(
            is_transient_aws_failure(
                "iam:create-role",
                "MalformedPolicyDocument: Invalid principal in policy",
            )
        )
        self.assertTrue(
            is_transient_aws_failure(
                "iam:attach-role-policy",
                "An error occurred (NoSuchEntity) while calling AttachRolePolicy",
            )
        )
        self.assertFalse(
            is_transient_aws_failure(
                "iam:create-role",
                "An error occurred (AccessDenied) while calling CreateRole",
            )
        )
        self.assertEqual(
            aws_error_code("An error occurred (AccessDenied) while calling CreateRole"),
            "AccessDenied",
        )

    def test_controller_plan_counts_all_missing_objects_without_writes(self) -> None:
        aws = MissingControllerAws()

        result = ensure_monthly_controllers(
            aws,  # type: ignore[arg-type]
            apply=False,
            account_id="111122223333",
            partition="aws",
            region="us-east-1",
            name_prefix="reactorfront",
            repository=EXPECTED_REPOSITORY,
            state_bucket="reactorfront-111122223333-us-east-1-state",
        )

        self.assertEqual(
            result,
            {"planned": 5, "plannedUpdates": 0, "created": 0},
        )
        self.assertFalse(
            any(
                operation.startswith(("create", "put", "tag"))
                for _, operation in aws.calls
            )
        )

    def test_every_owner_maintenance_call_pins_the_selected_region(self) -> None:
        aws = AwsCli("aws", region="us-east-1")
        completed = SimpleNamespace(returncode=0, stdout="{}", stderr="")

        with patch(
            "aws_automation_maintenance.subprocess.run", return_value=completed
        ) as run:
            aws.call("sts", "get-caller-identity")

        command = run.call_args.args[0]
        self.assertEqual(command.count("--region"), 1)
        self.assertEqual(command[command.index("--region") + 1], "us-east-1")

    def test_oidc_claim_guard_accepts_both_exact_event_subjects(self) -> None:
        for event_name in ("workflow_dispatch", "schedule"):
            claims = expected_claims(event_name)
            with self.subTest(event_name=event_name):
                validate_claims(claims, event_name)
                self.assertEqual(
                    claims["sub"],
                    expected_oidc_subject(event_name),
                )

    def test_oidc_repository_subject_keeps_names_and_pairs_immutable_ids(
        self,
    ) -> None:
        self.assertEqual(
            validate_repository_subject(
                EXPECTED_REPOSITORY,
                EXPECTED_IMMUTABLE_REPOSITORY_SUBJECT,
            ),
            EXPECTED_IMMUTABLE_REPOSITORY_SUBJECT,
        )
        for subject, error in (
            ("repo:other/Portfolio", "names drifted"),
            ("repo:Kentaro-Ono-jp@210682048/Portfolio", "IDs must be paired"),
        ):
            with (
                self.subTest(subject=subject),
                self.assertRaisesRegex(RuntimeError, error),
            ):
                validate_repository_subject(EXPECTED_REPOSITORY, subject)

    def test_oidc_claim_guard_rejects_every_identity_dimension(self) -> None:
        expected = expected_claims("workflow_dispatch")
        for key in expected:
            mutation = dict(expected)
            mutation[key] = "unexpected"
            with (
                self.subTest(key=key),
                self.assertRaisesRegex(RuntimeError, f"OIDC claim mismatch: {key}"),
            ):
                validate_claims(mutation, "workflow_dispatch")

    def test_oidc_claim_decoder_exposes_only_the_payload_object(self) -> None:
        payload = expected_claims("schedule")

        def encode(value: dict[str, str]) -> str:
            return (
                base64.urlsafe_b64encode(json.dumps(value).encode("utf-8"))
                .decode("ascii")
                .rstrip("=")
            )

        token = f"{encode({'alg': 'none'})}.{encode(payload)}.signature"

        self.assertEqual(decode_claims(token), payload)
        with self.assertRaisesRegex(RuntimeError, "token shape"):
            decode_claims("not-a-jwt")


if __name__ == "__main__":
    unittest.main()
