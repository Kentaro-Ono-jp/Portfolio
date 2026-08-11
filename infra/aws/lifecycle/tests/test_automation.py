from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from aws_automation_guard import (  # noqa: E402
    EXPECTED_ENVIRONMENT,
    EXPECTED_REF,
    EXPECTED_REPOSITORY,
    EXPECTED_WORKFLOW,
    PERMANENT_SCHEDULE,
    select_route,
)
from aws_automation_maintenance import lifecycle_config  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
