from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE_ROOT = REPOSITORY_ROOT / "infra" / "aws" / "lifecycle"
CONSOLE_IAM_ROOT = REPOSITORY_ROOT / "infra" / "aws" / "environment" / "console-iam"


def load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Lifecycle JSON must be an object: {path.name}")
    return value


def statement(policy: dict[str, object], sid: str) -> dict[str, object]:
    statements = [
        item
        for item in policy.get("Statement", [])
        if isinstance(item, dict) and item.get("Sid") == sid
    ]
    if len(statements) != 1:
        raise RuntimeError(f"Lifecycle IAM statement drifted: {sid}")
    return statements[0]


def main() -> int:
    required = (
        LIFECYCLE_ROOT / "README.md",
        LIFECYCLE_ROOT / "controller-contract.json",
        LIFECYCLE_ROOT / "image-build.buildspec.yml",
        LIFECYCLE_ROOT / "destroy.buildspec.yml",
        REPOSITORY_ROOT / "scripts" / "aws_lifecycle.py",
        REPOSITORY_ROOT / "scripts" / "aws_lifecycle_core.py",
    )
    missing = [
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in required
        if not path.is_file()
    ]
    if missing:
        raise RuntimeError(
            "Lifecycle contract files are missing: " + ", ".join(missing)
        )
    contract = load_json(LIFECYCLE_ROOT / "controller-contract.json")
    if contract.get("schemaVersion") != 1:
        raise RuntimeError("Unsupported lifecycle controller contract schema")
    if set(contract.get("projects", {})) != {"image", "destroy"}:
        raise RuntimeError(
            "Lifecycle controller must define exact image and destroy projects"
        )
    if contract.get("normalDeploymentIamMutation") is not False:
        raise RuntimeError("Lifecycle controller must keep normal deployment IAM-free")
    reconciliation = contract.get("imageBuildspecReconciliation", {})
    if reconciliation != {
        "actor": "operator_deployment",
        "project": "image",
        "requiresEveryOtherProjectFieldExact": True,
        "readBackExactSha256": True,
        "changesIamOrServiceRole": False,
    }:
        raise RuntimeError("Image buildspec reconciliation contract drifted")
    if contract.get("schedule", {}).get("actionAfterCompletion") != "NONE":
        raise RuntimeError("Fallback schedule must remain until zero residue is proved")
    if (
        contract.get("schedule", {}).get("group")
        != "${NAME_PREFIX}-${ENVIRONMENT}-lifecycle"
    ):
        raise RuntimeError("Fallback must use the exact persistent schedule group")
    if contract.get("schedule", {}).get("maximumTtlMinutes") != 120:
        raise RuntimeError("Fallback schedule must preserve the two-hour maximum")
    projects = contract.get("projects", {})
    if (
        projects.get("image", {}).get("autoRetryLimit") != 0
        or projects.get("destroy", {}).get("autoRetryLimit") != 2
    ):
        raise RuntimeError("Destroy controller must retain two automatic retries")
    manifest = load_json(CONSOLE_IAM_ROOT / "manifest.json")
    roles = manifest.get("roles", {})
    policies = manifest.get("managedPolicies", {})
    expected_attachments = {
        "operator_deployment": "lifecycleControl",
        "destroy": "lifecycleDestroy",
        "scheduler": "scheduler",
        "codebuild_image": "codebuildImage",
        "codebuild_destroy": "codebuildDestroy",
    }
    for role, policy in expected_attachments.items():
        role_value = roles.get(role, {}) if isinstance(roles, dict) else {}
        policy_value = policies.get(policy, {}) if isinstance(policies, dict) else {}
        if policy not in role_value.get("permissions", []) or not policy_value.get(
            "document"
        ):
            raise RuntimeError(f"Persistent lifecycle attachment drifted: {role}")
    lifecycle_policy = load_json(CONSOLE_IAM_ROOT / "lifecycle-control.json")
    image_reconciliation = statement(lifecycle_policy, "ReconcileExactImageBuildspec")
    if image_reconciliation.get("Action") != "codebuild:UpdateProject" or not str(
        image_reconciliation.get("Resource", "")
    ).endswith(":project/${NAME_PREFIX}-${ENVIRONMENT}-image-build"):
        raise RuntimeError("Image buildspec reconciliation is not exact-project only")
    schedule_group = statement(lifecycle_policy, "InspectExactLifecycleScheduleGroup")
    if set(schedule_group.get("Action", [])) != {
        "scheduler:GetScheduleGroup",
        "scheduler:ListTagsForResource",
    } or ":schedule-group/${NAME_PREFIX}-${ENVIRONMENT}-lifecycle" not in str(
        schedule_group.get("Resource", "")
    ):
        raise RuntimeError("Lifecycle schedule-group attestation drifted")
    schedule_management = statement(lifecycle_policy, "ManageExactFallbackSchedule")
    if ":schedule/${NAME_PREFIX}-${ENVIRONMENT}-lifecycle/" not in str(
        schedule_management.get("Resource", "")
    ):
        raise RuntimeError("Fallback schedule is not bound inside the exact group")
    scheduler_trust = load_json(CONSOLE_IAM_ROOT / "scheduler-trust.json")
    scheduler_statement = scheduler_trust.get("Statement", [{}])[0]
    trust_condition = scheduler_statement.get("Condition", {})
    source_arn = trust_condition.get("StringEquals", {}).get("aws:SourceArn")
    if (
        set(trust_condition) != {"StringEquals"}
        or source_arn
        != "arn:${AWS_PARTITION}:scheduler:${AWS_REGION}:${AWS_ACCOUNT_ID}:schedule-group/${NAME_PREFIX}-${ENVIRONMENT}-lifecycle"
    ):
        raise RuntimeError("Scheduler trust must use the exact schedule-group ARN")
    migration = statement(lifecycle_policy, "RunExactMigrationTask")
    if migration.get("Action") != "ecs:RunTask" or "ecs:cluster" not in json.dumps(
        migration.get("Condition", {}), sort_keys=True
    ):
        raise RuntimeError("Migration must bind RunTask to the exact cluster")
    lifecycle_destroy = load_json(CONSOLE_IAM_ROOT / "lifecycle-destroy.json")
    provider_destroy_reads = statement(
        lifecycle_destroy, "ReadOwnedProviderDestroyState"
    )
    if not {
        "cognito-idp:DescribeUserPool",
        "servicediscovery:ListInstances",
    }.issubset(set(provider_destroy_reads.get("Action", []))):
        raise RuntimeError("Owned provider destroy reads drifted")
    exact_destroy_reads = statement(
        lifecycle_destroy, "ReadExactNamedProviderDestroyState"
    )
    if not {
        "logs:ListTagsForResource",
        "secretsmanager:DescribeSecret",
    }.issubset(set(exact_destroy_reads.get("Action", []))):
        raise RuntimeError("Exact provider destroy reads drifted")
    image_cleanup = statement(lifecycle_destroy, "RemoveExactPublishedImages")
    if (
        set(image_cleanup.get("Action", []))
        != {
            "ecr:BatchDeleteImage",
            "ecr:DescribeImages",
        }
        or len(image_cleanup.get("Resource", [])) != 3
    ):
        raise RuntimeError("Destroy must remove and inventory three exact images")
    repository_inspection = statement(lifecycle_policy, "InspectExactImageRepositories")
    if (
        set(repository_inspection.get("Action", []))
        != {
            "ecr:DescribeRepositories",
            "ecr:GetLifecyclePolicy",
        }
        or len(repository_inspection.get("Resource", [])) != 3
    ):
        raise RuntimeError("Preflight must attest three exact image repositories")
    state_actions = {
        "s3:GetBucketLocation",
        "s3:GetBucketPublicAccessBlock",
        "s3:GetBucketVersioning",
        "s3:GetEncryptionConfiguration",
    }
    if (
        set(
            statement(lifecycle_policy, "InspectPersistentStateBucket").get(
                "Action", []
            )
        )
        != state_actions
    ):
        raise RuntimeError("Operator lifecycle state-bucket attestation drifted")
    if (
        set(
            statement(lifecycle_destroy, "InspectPersistentStateBucket").get(
                "Action", []
            )
        )
        != state_actions
    ):
        raise RuntimeError("Destroy lifecycle state-bucket attestation drifted")
    image_build = (LIFECYCLE_ROOT / "image-build.buildspec.yml").read_text(
        encoding="utf-8"
    )
    for token in ("exported-variables", "WEB_DIGEST", "API_DIGEST", "ML_DIGEST"):
        if token not in image_build:
            raise RuntimeError("Image build must export three immutable digests")
    lifecycle_source = (REPOSITORY_ROOT / "scripts" / "aws_lifecycle.py").read_text(
        encoding="utf-8"
    )
    destroy_build = (LIFECYCLE_ROOT / "destroy.buildspec.yml").read_text(
        encoding="utf-8"
    )
    terraform_archive = "terraform_1.15.8_linux_amd64.zip"
    if "runtime-versions:\n      python: 3.13" not in destroy_build:
        raise RuntimeError("Destroy controller Python runtime pin drifted")
    selected_python = "/root/.pyenv/versions/$PYTHON_313_VERSION/bin/python"
    if "python3" in destroy_build or destroy_build.count(selected_python) != 4:
        raise RuntimeError("Destroy controller selected-runtime entrypoint drifted")
    if "sys.version_info[:2] == (3, 13)" not in destroy_build:
        raise RuntimeError("Destroy controller runtime assertion drifted")
    required_aws_preflight = {
        "/usr/local/bin/aws --version",
        "/usr/local/bin/aws sts get-caller-identity",
        '/usr/local/bin/aws s3api get-object --bucket "$PORTFOLIO_STATE_BUCKET" --key "$PORTFOLIO_CONFIGURATION_KEY"',
        '/usr/local/bin/aws s3api get-object --bucket "$PORTFOLIO_STATE_BUCKET" --key "$LEASE_KEY"',
        '/usr/local/bin/aws sts assume-role --role-arn "$DESTROY_ROLE_ARN"',
        "--aws-cli /usr/local/bin/aws",
    }
    if not all(token in destroy_build for token in required_aws_preflight):
        raise RuntimeError("Destroy controller AWS CLI binding drifted")
    codebuild_destroy = load_json(CONSOLE_IAM_ROOT / "codebuild-destroy.json")
    lifecycle_inputs = statement(codebuild_destroy, "ReadExactLifecycleInputs")
    expected_inputs = {
        "arn:${AWS_PARTITION}:s3:::${STATE_BUCKET_NAME}/controls/${NAME_PREFIX}/${ENVIRONMENT}/configuration.json",
        "arn:${AWS_PARTITION}:s3:::${STATE_BUCKET_NAME}/controls/${NAME_PREFIX}/${ENVIRONMENT}/lease.json",
    }
    if (
        lifecycle_inputs.get("Action") != "s3:GetObject"
        or set(lifecycle_inputs.get("Resource", [])) != expected_inputs
    ):
        raise RuntimeError("Destroy controller lifecycle input authority drifted")
    if destroy_build.count(f"/tmp/{terraform_archive}") != 3 or (
        f"grep '{terraform_archive}$' terraform.sha256sums | sha256sum --check"
        not in destroy_build
    ):
        raise RuntimeError("Destroy controller Terraform checksum binding drifted")
    forbidden_iam_writes = (
        '"create-policy"',
        '"create-role"',
        '"attach-role-policy"',
        '"put-role-policy"',
        '"put-role-permissions-boundary"',
        '"update-assume-role-policy"',
    )
    if any(token in lifecycle_source for token in forbidden_iam_writes):
        raise RuntimeError("Normal lifecycle contains an IAM mutation command")
    for token in (
        '"update-project"',
        "reconcile_image_buildspec=True",
        "previousBuildspecSha256",
        "currentBuildspecSha256",
    ):
        if token not in lifecycle_source:
            raise RuntimeError("Exact image buildspec reconciliation drifted")
    for token in ('"batch-delete-image"', '"describe-images"', "config.image_tag"):
        if token not in lifecycle_source:
            raise RuntimeError("Lifecycle zero-residue image proof drifted")
    for token in (
        "read_exact_image_digests",
        '"imagePublication"',
        '"fallbackIntent"',
        "ensure_schedule",
        '"fallbackRegistration"',
    ):
        if token not in lifecycle_source:
            raise RuntimeError("Lifecycle effect-before-checkpoint recovery drifted")
    for token in (
        '"-refresh=false"',
        "retain_private_process_diagnostic",
        "aws_secretsmanager_secret_version.broker",
        "aws_secretsmanager_secret_version.database",
    ):
        if token not in lifecycle_source:
            raise RuntimeError("Lifecycle private destroy diagnostics drifted")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "infra/aws/lifecycle/tests",
            "-p",
            "test_*.py",
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    result = {
        "schemaVersion": 2,
        "controllerProjects": 2,
        "controllerLogGroups": 2,
        "persistentScheduleGroups": 1,
        "destroyControllerAutoRetries": 2,
        "maximumTtlMinutes": 120,
        "normalDeploymentIamMutation": False,
        "persistentIamAttachments": len(expected_attachments),
        "immutableDigestExports": 3,
        "immutableImageResidueChecks": 3,
        "persistentImageRepositoryChecks": 3,
        "persistentStateBucketChecks": 4,
        "staticVerifierAwsApiCalls": 0,
        "staticVerifierAwsWrites": 0,
        "staticVerifierAwsResourcesCreated": 0,
        "liveAwsHistoryIncluded": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
    ) as error:
        print(f"AWS lifecycle verification failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
