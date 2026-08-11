from __future__ import annotations

import re

EXPECTED_REPOSITORY_OWNER = "Kentaro-Ono-jp"
EXPECTED_REPOSITORY_OWNER_ID = "210682048"
EXPECTED_REPOSITORY_NAME = "Portfolio"
EXPECTED_REPOSITORY_ID = "1304682496"
EXPECTED_REPOSITORY = f"{EXPECTED_REPOSITORY_OWNER}/{EXPECTED_REPOSITORY_NAME}"
EXPECTED_IMMUTABLE_REPOSITORY_SUBJECT = (
    f"repo:{EXPECTED_REPOSITORY_OWNER}@{EXPECTED_REPOSITORY_OWNER_ID}/"
    f"{EXPECTED_REPOSITORY_NAME}@{EXPECTED_REPOSITORY_ID}"
)
EXPECTED_REF = "refs/heads/main"
EXPECTED_ENVIRONMENT = "aws-deployment"
EXPECTED_WORKFLOW = "Deploy managed AWS proof"
EXPECTED_WORKFLOW_REF = (
    f"{EXPECTED_REPOSITORY}/.github/workflows/aws-deploy.yml@{EXPECTED_REF}"
)
EXPECTED_AUDIENCE = "sts.amazonaws.com"
EXPECTED_EVENTS = frozenset({"workflow_dispatch", "schedule"})
OIDC_SUBJECT_TEMPLATE_KEYS = ("repo", "context", "job_workflow_ref", "event_name")
PERMANENT_SCHEDULE = "0 13 1 * *"


def expected_oidc_subject(event_name: str) -> str:
    if event_name not in EXPECTED_EVENTS:
        raise RuntimeError("OIDC event claim is not accepted")
    return (
        f"{EXPECTED_IMMUTABLE_REPOSITORY_SUBJECT}:"
        f"environment:{EXPECTED_ENVIRONMENT}:"
        f"job_workflow_ref:{EXPECTED_WORKFLOW_REF}:event_name:{event_name}"
    )


def validate_repository_subject(repository: str, subject: str) -> str:
    match = re.fullmatch(
        r"repo:(?P<owner>[A-Za-z0-9_.-]+)(?:@(?P<owner_id>[0-9]+))?/"
        r"(?P<repository>[A-Za-z0-9_.-]+)(?:@(?P<repository_id>[0-9]+))?",
        subject,
    )
    if match is None:
        raise RuntimeError("GitHub OIDC repository subject shape is invalid")
    expected_owner, expected_repository = repository.split("/", maxsplit=1)
    if (
        match.group("owner") != expected_owner
        or match.group("repository") != expected_repository
    ):
        raise RuntimeError("GitHub OIDC repository subject names drifted")
    if bool(match.group("owner_id")) != bool(match.group("repository_id")):
        raise RuntimeError("GitHub OIDC immutable subject IDs must be paired")
    return subject
