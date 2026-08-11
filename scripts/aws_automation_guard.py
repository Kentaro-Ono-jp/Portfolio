from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from aws_automation_contract import (
    EXPECTED_ENVIRONMENT,
    EXPECTED_REF,
    EXPECTED_REPOSITORY,
    EXPECTED_REPOSITORY_OWNER,
    EXPECTED_WORKFLOW,
    PERMANENT_SCHEDULE,
)

SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class AutomationRoute:
    event_name: str
    mode: str
    schedule_kind: str


def select_route(values: Mapping[str, str]) -> AutomationRoute:
    event_name = values.get("GITHUB_EVENT_NAME", "")
    repository = values.get("GITHUB_REPOSITORY", "")
    repository_owner = values.get("GITHUB_REPOSITORY_OWNER", "")
    actor = values.get("GITHUB_ACTOR", "")
    triggering_actor = values.get("GITHUB_TRIGGERING_ACTOR", "")
    ref = values.get("GITHUB_REF", "")
    workflow = values.get("GITHUB_WORKFLOW", "")
    sha = values.get("GITHUB_SHA", "")
    configured_environment = values.get("PORTFOLIO_GITHUB_ENVIRONMENT", "")
    if repository != EXPECTED_REPOSITORY:
        raise RuntimeError("Automation repository identity is not accepted.")
    if repository_owner != EXPECTED_REPOSITORY_OWNER:
        raise RuntimeError("Automation repository owner is not accepted.")
    if ref != EXPECTED_REF:
        raise RuntimeError("Automation ref is not the exact main branch.")
    if workflow != EXPECTED_WORKFLOW:
        raise RuntimeError("Automation workflow identity is not accepted.")
    if configured_environment != EXPECTED_ENVIRONMENT:
        raise RuntimeError("Automation protected environment is not accepted.")
    if SHA_PATTERN.fullmatch(sha) is None:
        raise RuntimeError("Automation source SHA is not a full commit identity.")

    if event_name == "workflow_dispatch":
        if actor != repository_owner or triggering_actor != repository_owner:
            raise RuntimeError("Only the repository owner may dispatch deployment.")
        return AutomationRoute(event_name, "manual", "not-scheduled")
    if event_name != "schedule":
        raise RuntimeError("Automation event is not accepted.")

    schedule = values.get("GITHUB_EVENT_SCHEDULE", "")
    permanent = values.get("PORTFOLIO_PERMANENT_SCHEDULE", "")
    temporary = values.get("PORTFOLIO_TEMPORARY_SCHEDULE", "")
    if permanent != PERMANENT_SCHEDULE:
        raise RuntimeError("Permanent monthly schedule contract drifted.")
    if temporary and temporary == permanent:
        raise RuntimeError("Temporary schedule must be distinct when enabled.")
    if schedule == permanent:
        kind = "permanent"
    elif temporary and schedule == temporary:
        kind = "temporary"
    else:
        raise RuntimeError("Scheduled automation cron is not repository-owned.")
    return AutomationRoute(event_name, "monthly", kind)


def git_output(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        capture_output=True,
        check=True,
        text=True,
    )
    return completed.stdout.strip()


def verify_checkout(values: Mapping[str, str]) -> None:
    expected_sha = values["GITHUB_SHA"]
    if git_output("rev-parse", "HEAD") != expected_sha:
        raise RuntimeError("Checked-out commit is not github.sha.")
    if git_output("status", "--porcelain", "--untracked-files=all"):
        raise RuntimeError("Automation checkout is not clean.")
    remote = git_output("remote", "get-url", "origin")
    if remote not in {
        f"https://github.com/{EXPECTED_REPOSITORY}",
        f"https://github.com/{EXPECTED_REPOSITORY}.git",
        f"git@github.com:{EXPECTED_REPOSITORY}.git",
    }:
        raise RuntimeError("Automation checkout remote is not accepted.")


def append(path: str, value: str) -> None:
    with Path(path).open("a", encoding="utf-8", newline="\n") as target:
        target.write(value)


def main() -> int:
    try:
        route = select_route(os.environ)
        verify_checkout(os.environ)
        output_path = os.environ.get("GITHUB_OUTPUT", "")
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")
        if not output_path or not summary_path:
            raise RuntimeError("GitHub output surfaces are unavailable.")
        append(output_path, f"mode={route.mode}\n")
        append(output_path, f"caller_event={route.event_name}\n")
        append(output_path, f"schedule_kind={route.schedule_kind}\n")
        append(
            summary_path,
            "## Managed AWS proof guard\n\n"
            f"- Event: `{route.event_name}`\n"
            f"- Isolated mode: `{route.mode}`\n"
            f"- Schedule class: `{route.schedule_kind}`\n",
        )
        return 0
    except (KeyError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
        message = " ".join(str(error).splitlines()) or error.__class__.__name__
        print(f"Automation guard failed safely: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
