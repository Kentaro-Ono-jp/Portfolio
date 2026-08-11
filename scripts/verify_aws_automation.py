from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from aws_automation_contract import (
    EXPECTED_IMMUTABLE_REPOSITORY_SUBJECT,
    expected_oidc_subject,
)
from aws_automation_maintenance import (
    WRITE_OPERATIONS,
    build_contract,
    ordered_role_specs,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "aws-deploy.yml"
CONTRACT_PATH = REPOSITORY_ROOT / "scripts" / "aws_automation_contract.py"
GUARD_PATH = REPOSITORY_ROOT / "scripts" / "aws_automation_guard.py"
OIDC_CLAIM_PATH = REPOSITORY_ROOT / "scripts" / "aws_oidc_claim_guard.py"
MAINTENANCE_PATH = REPOSITORY_ROOT / "scripts" / "aws_automation_maintenance.py"
LIFECYCLE_PATH = REPOSITORY_ROOT / "scripts" / "aws_lifecycle.py"
BOOTSTRAP_LOCALS_PATH = REPOSITORY_ROOT / "infra" / "aws" / "bootstrap" / "locals.tf"

CHECKOUT_STEP = "Check out the exact source"
GUARD_STEP = "Guard the exact automation route"
OIDC_CLAIM_STEP = "Verify the exact GitHub OIDC claims"
OIDC_STEP = "Obtain the short-lived GitHub OIDC session"


def workflow_step_names(source: str) -> list[str]:
    return re.findall(r"(?m)^      - name: (.+)$", source)


def verify_workflow_gate_order(names: list[str]) -> None:
    for expected in (CHECKOUT_STEP, GUARD_STEP, OIDC_CLAIM_STEP, OIDC_STEP):
        if names.count(expected) != 1:
            raise RuntimeError(f"Deployment workflow step is not exact: {expected}")
    checkout = names.index(CHECKOUT_STEP)
    guard = names.index(GUARD_STEP)
    claim = names.index(OIDC_CLAIM_STEP)
    oidc = names.index(OIDC_STEP)
    if guard <= checkout:
        raise RuntimeError("Automation route guard must run after exact checkout")
    if guard >= oidc:
        raise RuntimeError("Automation route guard must run before OIDC assumption")
    if claim <= guard:
        raise RuntimeError("OIDC claim guard must run after the route guard")
    if claim >= oidc:
        raise RuntimeError("OIDC claim guard must run before OIDC assumption")


def verify_workflow_order_mutations(names: list[str]) -> int:
    cases = 0
    before_checkout = list(names)
    before_checkout.remove(GUARD_STEP)
    before_checkout.insert(before_checkout.index(CHECKOUT_STEP), GUARD_STEP)
    after_oidc = list(names)
    after_oidc.remove(GUARD_STEP)
    after_oidc.insert(after_oidc.index(OIDC_STEP) + 1, GUARD_STEP)
    claim_after_oidc = list(names)
    claim_after_oidc.remove(OIDC_CLAIM_STEP)
    claim_after_oidc.insert(claim_after_oidc.index(OIDC_STEP) + 1, OIDC_CLAIM_STEP)
    for label, mutation, expected in (
        ("before checkout", before_checkout, "after exact checkout"),
        ("after OIDC", after_oidc, "before OIDC assumption"),
        ("claim after OIDC", claim_after_oidc, "before OIDC assumption"),
    ):
        try:
            verify_workflow_gate_order(mutation)
        except RuntimeError as error:
            if expected not in str(error):
                raise RuntimeError(
                    f"Workflow order mutation failed for the wrong reason: {label}"
                ) from error
            cases += 1
        else:
            raise RuntimeError(f"Workflow order mutation was accepted: {label}")
    return cases


def require(source: str, token: str, message: str) -> None:
    if token not in source:
        raise RuntimeError(message)


def main() -> int:
    for path in (
        WORKFLOW_PATH,
        CONTRACT_PATH,
        GUARD_PATH,
        OIDC_CLAIM_PATH,
        MAINTENANCE_PATH,
        LIFECYCLE_PATH,
        BOOTSTRAP_LOCALS_PATH,
    ):
        if not path.is_file():
            raise RuntimeError(f"AWS automation contract is missing: {path.name}")
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    guard = GUARD_PATH.read_text(encoding="utf-8")
    oidc_claim = OIDC_CLAIM_PATH.read_text(encoding="utf-8")
    maintenance = MAINTENANCE_PATH.read_text(encoding="utf-8")
    lifecycle = LIFECYCLE_PATH.read_text(encoding="utf-8")
    bootstrap = BOOTSTRAP_LOCALS_PATH.read_text(encoding="utf-8")

    if not workflow.startswith("name: Deploy managed AWS proof\n"):
        raise RuntimeError("Deployment workflow display name drifted")
    step_names = workflow_step_names(workflow)
    verify_workflow_gate_order(step_names)
    order_mutation_cases = verify_workflow_order_mutations(step_names)
    trigger_match = re.search(r"(?ms)^on:\n(?P<body>.+?)^permissions:\n", workflow)
    if trigger_match is None:
        raise RuntimeError("Deployment workflow trigger block is unavailable")
    triggers = trigger_match.group("body")
    for accepted in ("workflow_dispatch:", "schedule:"):
        require(triggers, accepted, f"Deployment trigger is missing: {accepted}")
    for forbidden in (
        "push:",
        "pull_request:",
        "pull_request_target:",
        "workflow_run:",
        "repository_dispatch:",
    ):
        if forbidden in triggers:
            raise RuntimeError(f"Forbidden AWS deployment trigger exists: {forbidden}")
    require(triggers, 'cron: "0 13 1 * *"', "Permanent monthly cron drifted")
    require(triggers, 'timezone: "Asia/Tokyo"', "Monthly timezone drifted")

    permission_match = re.search(
        r"(?ms)^permissions:\n(?P<body>.+?)^concurrency:\n", workflow
    )
    if permission_match is None:
        raise RuntimeError("Deployment permission block is unavailable")
    permissions = {
        line.strip()
        for line in permission_match.group("body").splitlines()
        if line.strip()
    }
    if permissions != {"contents: read", "id-token: write"}:
        raise RuntimeError("Deployment workflow permissions are not minimal")
    for token in (
        "group: managed-aws-proof",
        "cancel-in-progress: false",
        "environment: aws-deployment",
        "timeout-minutes: 180",
        "persist-credentials: false",
        "ref: ${{ github.sha }}",
        "python3 scripts/aws_automation_guard.py",
        "python3 scripts/aws_oidc_claim_guard.py",
        "aws-actions/configure-aws-credentials@v6.2.3",
        "audience: sts.amazonaws.com",
        "role-to-assume: ${{ vars.AWS_AUTOMATION_ROLE_ARN }}",
        "role-session-name: portfolio-github-${{ github.run_id }}",
        "mask-aws-account-id: true",
        "output-credentials: false",
        "unset-current-credentials: true",
        "--caller-mode github-automation",
        '--automation-event "${{ steps.guard.outputs.caller_event }}"',
        '--environment "${{ steps.guard.outputs.mode }}"',
        "deploy",
        "destroy --mode manual",
        "sweep",
        "id: configure",
        "if: always() && steps.configure.outcome == 'success'",
    ):
        require(workflow, token, f"Deployment workflow contract drifted: {token}")
    if workflow.count("aws-actions/configure-aws-credentials@v6.2.3") != 2:
        raise RuntimeError("Deployment and cleanup need two short-lived OIDC sessions")
    if workflow.count("if: always() && steps.configure.outcome == 'success'") != 3:
        raise RuntimeError(
            "AWS cleanup must require successful credential configuration"
        )
    if "steps.guard.outcome == 'success'" in workflow:
        raise RuntimeError("AWS cleanup must not run after an OIDC setup failure")
    for forbidden in (
        "AWS_ACCESS_KEY_ID:",
        "AWS_SECRET_ACCESS_KEY:",
        "secrets.AWS_",
        "awsinfo",
        "pull_request",
    ):
        if forbidden in workflow:
            raise RuntimeError(
                f"Deployment workflow contains a forbidden input: {forbidden}"
            )

    for token in (
        'return AutomationRoute(event_name, "manual", "not-scheduled")',
        'return AutomationRoute(event_name, "monthly", kind)',
        "Only the repository owner may dispatch deployment.",
        "Scheduled automation cron is not repository-owned.",
    ):
        require(guard, token, f"Automation guard contract drifted: {token}")

    for token in (
        "expected_oidc_subject(event_name)",
        '"audience": EXPECTED_AUDIENCE',
        "validate_claims(decode_claims(token), event_name)",
        "OIDC claim mismatch:",
    ):
        require(oidc_claim, token, f"OIDC claim guard contract drifted: {token}")

    for token in (
        'EXPECTED_REPOSITORY_OWNER = "Kentaro-Ono-jp"',
        'EXPECTED_REPOSITORY_OWNER_ID = "210682048"',
        'EXPECTED_REPOSITORY_NAME = "Portfolio"',
        'EXPECTED_REPOSITORY_ID = "1304682496"',
        'EXPECTED_REF = "refs/heads/main"',
        'EXPECTED_ENVIRONMENT = "aws-deployment"',
        'EXPECTED_WORKFLOW = "Deploy managed AWS proof"',
        'EXPECTED_AUDIENCE = "sts.amazonaws.com"',
        'EXPECTED_EVENTS = frozenset({"workflow_dispatch", "schedule"})',
        'PERMANENT_SCHEDULE = "0 13 1 * *"',
        "validate_repository_subject",
    ):
        require(contract, token, f"Shared automation contract drifted: {token}")

    for token in (
        'parser.error("--apply requires --owner-checkpoint issue-116")',
        'caller_arn.endswith(":user/ReactorFrontNoel")',
        '"mode": "apply" if args.apply else "plan"',
        '"accountSpecificValuesPublished": False',
        '"awsRegionPinned": args.region',
        '"postWriteReadback": args.apply',
        '"githubImmutableSubject"',
        "args.github_oidc_repository_subject",
        "aws = AwsCli(args.aws_cli, region=args.region)",
        'lifecycle_env["AWS_DEFAULT_REGION"] = args.region',
        "lifecycle.verify_controller(config, reader)",
        "lifecycle.verify_image_repositories(config, reader)",
        "lifecycle.verify_state_bucket(config, reader)",
    ):
        require(maintenance, token, f"Static maintenance boundary drifted: {token}")
    if "aws_automation_maintenance.py" in workflow:
        raise RuntimeError("Normal automation must not mutate the static IAM contract")
    expected_writes = {
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
        "logs:untag-resource",
        "scheduler:create-schedule-group",
        "scheduler:tag-resource",
        "scheduler:untag-resource",
        "codebuild:create-project",
        "codebuild:update-project",
    }
    if WRITE_OPERATIONS != expected_writes:
        raise RuntimeError("Static maintenance write inventory drifted")
    policies, roles = build_contract(
        "111122223333",
        "aws",
        "us-east-1",
        "reactorfront",
        "Kentaro-Ono-jp/Portfolio",
        "reactorfront-111122223333-us-east-1-state",
        EXPECTED_IMMUTABLE_REPOSITORY_SUBJECT,
    )
    if len(policies) != 33 or len(roles) != 19:
        raise RuntimeError("Static maintenance inventory is incomplete")
    ordered_names = [
        str(spec["name"])
        for spec in ordered_role_specs(
            roles,
            account_id="111122223333",
            partition="aws",
        )
    ]
    if ordered_names[0] != "reactorfront-automation":
        raise RuntimeError("Automation role must exist before target trust updates")
    for environment in ("manual", "monthly"):
        operator = f"reactorfront-{environment}-operator-deployment"
        destroy = f"reactorfront-{environment}-destroy"
        codebuild = f"reactorfront-{environment}-codebuild-destroy"
        scheduler = f"reactorfront-{environment}-scheduler"
        if not (
            ordered_names.index(operator) < ordered_names.index(destroy)
            and ordered_names.index(codebuild) < ordered_names.index(destroy)
            and ordered_names.index(scheduler) < ordered_names.index(destroy)
        ):
            raise RuntimeError("Static role dependency order drifted")
    automation = roles.get("reactorfront-automation", {})
    if automation.get("permissions") != ["ReactorFrontPortfolioAutomation"]:
        raise RuntimeError("Automation role attachment drifted")
    if automation.get("boundary") != "ReactorFrontPortfolioAutomationBoundary":
        raise RuntimeError("Automation role boundary drifted")
    automation_subjects = automation["trust"]["Statement"][0]["Condition"][
        "StringEquals"
    ]["token.actions.githubusercontent.com:sub"]
    if set(automation_subjects) != {
        expected_oidc_subject("workflow_dispatch"),
        expected_oidc_subject("schedule"),
    }:
        raise RuntimeError("Immutable GitHub OIDC subjects drifted")

    for token in (
        "CALLER_MODE_GITHUB_AUTOMATION",
        'r"portfolio-github-[0-9]+$"',
        "default=60, choices=range(15, 121)",
        '"--caller-mode"',
        '"--automation-event"',
    ):
        require(lifecycle, token, f"Lifecycle automation boundary drifted: {token}")
    if lifecycle.count("default=60, choices=range(15, 121)") != 2:
        raise RuntimeError("Deploy and fallback must both default to one hour")

    for token in (
        "operator_trust_policies",
        'Sid       = "ExactGitHubAutomationRole"',
        "Principal = { AWS = local.global_role_arns.automation }",
        'role.purpose == "operator-deployment" ? local.operator_trust_policies',
    ):
        require(bootstrap, token, f"Bootstrap target trust drifted: {token}")

    subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "infra/aws/lifecycle/tests",
            "-p",
            "test_automation.py",
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    result = {
        "schemaVersion": 1,
        "acceptedEventTypes": 2,
        "isolatedModes": 2,
        "permanentSchedules": 1,
        "normalTtlMinutes": 60,
        "oidcCredentialRefreshes": 2,
        "workflowOrderMutationCases": order_mutation_cases,
        "requiredReviewers": 0,
        "waitTimerMinutes": 0,
        "staticVerifierAwsApiCalls": 0,
        "staticVerifierAwsWrites": 0,
        "staticVerifierAwsResourcesCreated": 0,
        "ownerMaintenanceManagedPolicies": len(policies),
        "ownerMaintenancePersistentRoles": len(roles),
        "liveAwsHistoryIncluded": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"AWS automation verification failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
