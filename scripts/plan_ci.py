from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import verify


FULL_SHA = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True)
class CIContext:
    event_name: str
    event_action: str
    pr_base_sha: str
    pr_head_sha: str
    pr_author: str
    before_sha: str
    current_sha: str
    actor: str
    repository_owner: str
    repository: str

    @classmethod
    def from_environment(cls) -> CIContext:
        values = {
            name.lower(): os.environ.get(name, "")
            for name in (
                "EVENT_NAME",
                "EVENT_ACTION",
                "PR_BASE_SHA",
                "PR_HEAD_SHA",
                "PR_AUTHOR",
                "BEFORE_SHA",
                "CURRENT_SHA",
                "ACTOR",
                "REPOSITORY_OWNER",
                "REPOSITORY",
            )
        }
        return cls(**values)


@dataclass(frozen=True)
class CIPlanRequest:
    reason: str
    base: str | None = None
    full: bool = False
    carry_all: bool = False
    baseline_proven: bool = False
    baseline_skipped_groups: str = ""
    current_skipped_groups: str = ""
    close_baseline_gaps: bool = False

    def resolve(self) -> verify.VerificationPlan:
        return verify.resolve_selection(
            argparse.Namespace(
                static_only=False,
                groups=None,
                plan=True,
                base=self.base,
                staged=False,
                full=self.full,
                carry_all=self.carry_all,
                baseline_proven=self.baseline_proven,
                baseline_skipped_groups=self.baseline_skipped_groups or None,
                close_baseline_gaps=self.close_baseline_gaps,
                carried_groups=None,
                skipped_groups=self.current_skipped_groups or None,
                github_output=None,
                summary=None,
            )
        )


def command_text(command: list[str]) -> str:
    result = subprocess.run(
        command,
        cwd=verify.REPOSITORY_ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def require_sha(value: str, label: str) -> str:
    if FULL_SHA.fullmatch(value) is None:
        raise RuntimeError(f"{label} is not a full commit SHA: {value or 'missing'}")
    return value


def usable_before_sha(value: str) -> bool:
    return FULL_SHA.fullmatch(value) is not None and set(value) != {"0"}


def is_repository_owner(login: str, repository_owner: str) -> bool:
    return bool(login) and login.casefold() == repository_owner.casefold()


def latest_run_succeeded(repository: str, candidate_sha: str) -> bool:
    require_sha(candidate_sha, "Verification baseline")
    try:
        conclusion = command_text(
            [
                "gh",
                "api",
                "--method",
                "GET",
                f"repos/{repository}/actions/workflows/verify.yml/runs",
                "-f",
                f"head_sha={candidate_sha}",
                "-f",
                "per_page=1",
                "--jq",
                '.workflow_runs[0].conclusion // ""',
            ]
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    return conclusion == "success"


def commit_message(repository: str, candidate_sha: str) -> str:
    require_sha(candidate_sha, "Trailer commit")
    local = subprocess.run(
        ["git", "cat-file", "-e", f"{candidate_sha}^{{commit}}"],
        cwd=verify.REPOSITORY_ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if local.returncode == 0:
        return command_text(["git", "show", "-s", "--format=%B", candidate_sha])
    return command_text(
        [
            "gh",
            "api",
            f"repos/{repository}/commits/{candidate_sha}",
            "--jq",
            ".commit.message",
        ]
    )


def trailer_value(repository: str, candidate_sha: str, key: str) -> str:
    parsed = subprocess.run(
        ["git", "interpret-trailers", "--parse"],
        cwd=verify.REPOSITORY_ROOT,
        check=True,
        input=commit_message(repository, candidate_sha),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout
    prefix = f"{key}: "
    values = [
        line.removeprefix(prefix)
        for line in parsed.splitlines()
        if line.startswith(prefix)
    ]
    return values[-1] if values else ""


def merged_pr_for_commit(repository: str, current_sha: str) -> tuple[str, str] | None:
    try:
        value = command_text(
            [
                "gh",
                "api",
                "--method",
                "GET",
                f"repos/{repository}/commits/{current_sha}/pulls",
                "--jq",
                (
                    '[.[] | select(.merged_at != null and .base.ref == "main")][0] '
                    '| if . == null then "" else [.head.sha, .user.login] | @tsv end'
                ),
            ]
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    fields = value.split("\t") if value else []
    if len(fields) != 2 or FULL_SHA.fullmatch(fields[0]) is None or not fields[1]:
        return None
    return fields[0], fields[1]


def local_commit_tree(current_sha: str) -> str:
    require_sha(current_sha, "Current commit")
    return command_text(["git", "rev-parse", f"{current_sha}^{{tree}}"])


def remote_commit_tree(repository: str, candidate_sha: str) -> str | None:
    try:
        return command_text(
            [
                "gh",
                "api",
                f"repos/{repository}/git/commits/{candidate_sha}",
                "--jq",
                ".tree.sha",
            ]
        )
    except (OSError, subprocess.CalledProcessError):
        return None


def pull_request_plan(context: CIContext) -> CIPlanRequest:
    require_sha(context.pr_base_sha, "PR base")
    require_sha(context.pr_head_sha, "PR head")
    owner_pr = is_repository_owner(context.pr_author, context.repository_owner)
    synchronize = (
        owner_pr
        and context.event_action == "synchronize"
        and usable_before_sha(context.before_sha)
    )
    base = context.before_sha if synchronize else context.pr_base_sha
    reason = "previous owner PR head" if synchronize else "PR base"

    if latest_run_succeeded(context.repository, base):
        baseline_skips = trailer_value(context.repository, base, "Verification-Skip")
        current_skips = (
            trailer_value(context.repository, context.pr_head_sha, "Verification-Skip")
            if owner_pr
            else ""
        )
        return CIPlanRequest(
            reason=reason,
            base=base,
            baseline_proven=True,
            baseline_skipped_groups=baseline_skips,
            current_skipped_groups=current_skips,
            close_baseline_gaps=bool(baseline_skips) and not owner_pr,
        )

    if not owner_pr:
        raise RuntimeError(
            f"{reason} {base} lacks a latest successful Verify run; "
            "no checks or Docker were started."
        )
    return CIPlanRequest(
        reason=f"owner cold full; {reason} {base} lacks a successful Verify run",
        full=True,
        current_skipped_groups=trailer_value(
            context.repository, context.pr_head_sha, "Verification-Skip"
        ),
    )


def push_plan(context: CIContext) -> CIPlanRequest:
    require_sha(context.current_sha, "Current push commit")
    if not is_repository_owner(context.actor, context.repository_owner):
        raise RuntimeError("Only the repository owner may establish main evidence.")
    merged_pr = merged_pr_for_commit(context.repository, context.current_sha)
    if merged_pr is not None:
        pr_head, pr_author = merged_pr
        pr_tree = remote_commit_tree(context.repository, pr_head)
        if (
            is_repository_owner(pr_author, context.repository_owner)
            and pr_tree is not None
            and local_commit_tree(context.current_sha) == pr_tree
            and latest_run_succeeded(context.repository, pr_head)
        ):
            baseline_skips = trailer_value(
                context.repository, pr_head, "Verification-Skip"
            )
            current_skips = trailer_value(
                context.repository, context.current_sha, "Verification-Skip"
            )
            return CIPlanRequest(
                reason=f"tree-identical successful PR head {pr_head}",
                carry_all=True,
                baseline_proven=True,
                baseline_skipped_groups=baseline_skips,
                current_skipped_groups=current_skips,
            )

    if not usable_before_sha(context.before_sha):
        raise RuntimeError(
            "main push has no usable baseline; no checks or Docker were started."
        )
    if not latest_run_succeeded(context.repository, context.before_sha):
        raise RuntimeError(
            f"main baseline {context.before_sha} lacks a latest successful Verify run; "
            "no checks or Docker were started."
        )
    baseline_skips = trailer_value(
        context.repository, context.before_sha, "Verification-Skip"
    )
    current_skips = trailer_value(
        context.repository, context.current_sha, "Verification-Skip"
    )
    return CIPlanRequest(
        reason=f"successful main baseline {context.before_sha}",
        base=context.before_sha,
        baseline_proven=True,
        baseline_skipped_groups=baseline_skips,
        current_skipped_groups=current_skips,
    )


def select_ci_plan(context: CIContext) -> CIPlanRequest:
    if not context.repository or "/" not in context.repository:
        raise RuntimeError("GitHub repository identity is unavailable.")
    if not context.repository_owner:
        raise RuntimeError("GitHub repository owner is unavailable.")
    if not is_repository_owner(
        context.repository.split("/", maxsplit=1)[0], context.repository_owner
    ):
        raise RuntimeError(
            "GitHub repository owner does not match repository identity."
        )
    if context.event_name == "pull_request":
        return pull_request_plan(context)
    if context.event_name == "push":
        return push_plan(context)
    if context.event_name == "workflow_dispatch":
        if not is_repository_owner(context.actor, context.repository_owner):
            raise RuntimeError(
                "Only the repository owner may dispatch full verification."
            )
        return CIPlanRequest(reason="owner-dispatched full verification", full=True)
    raise RuntimeError(f"Unsupported workflow event: {context.event_name or 'missing'}")


def append_summary(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as summary:
        summary.write(text)


def github_error(message: str) -> str:
    escaped = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return f"::error::{escaped}"


def main() -> int:
    output_value = os.environ.get("GITHUB_OUTPUT", "")
    summary_value = os.environ.get("GITHUB_STEP_SUMMARY", "")
    try:
        if not output_value or not summary_value:
            raise RuntimeError("GitHub output or step-summary path is unavailable.")
        request = select_ci_plan(CIContext.from_environment())
        plan = request.resolve()
        for line in verify.plan_lines(plan):
            print(line)
        verify.write_plan_outputs(plan, Path(output_value))
        verify.write_plan_summary(plan, Path(summary_value))
        append_summary(
            Path(summary_value), f"\n- Selection baseline: {request.reason}\n"
        )
        return 0
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as error:
        message = " ".join(str(error).splitlines()) or error.__class__.__name__
        if summary_value:
            try:
                append_summary(
                    Path(summary_value),
                    f"## Selective verification stopped\n\n- {message}\n",
                )
            except OSError as summary_error:
                message += f"; step summary unavailable: {summary_error}"
        print(github_error(message), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
