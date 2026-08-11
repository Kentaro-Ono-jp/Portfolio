from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PARENT = REPOSITORY_ROOT / "infra" / "aws" / "environment"
CONTRACT_ROOTS = {
    "manual": CONTRACT_PARENT / "console-iam",
    "monthly": CONTRACT_PARENT / "console-iam-monthly",
}
MUTATION_PREFIXES = (
    "add",
    "attach",
    "create",
    "delete",
    "detach",
    "put",
    "remove",
    "set",
    "tag",
    "untag",
    "update",
)
USER_READ_ACTIONS = {
    "iam:GetLoginProfile",
    "iam:GetUser",
    "iam:ListAccessKeys",
    "iam:ListAttachedUserPolicies",
    "iam:ListGroupsForUser",
    "iam:ListUserPolicies",
}
ROLE_READ_ACTIONS = {
    "iam:GetRole",
    "iam:ListAttachedRolePolicies",
    "iam:ListRolePolicies",
    "iam:ListRoleTags",
}
POLICY_READ_ACTIONS = {
    "iam:GetPolicy",
    "iam:GetPolicyVersion",
    "iam:ListEntitiesForPolicy",
    "iam:ListPolicyTags",
    "iam:ListPolicyVersions",
}


def values(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else [str(value)]


def canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()


def sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def normalized_iam_document(payload: Any) -> Any:
    """Normalize IAM's semantically unordered JSON arrays for live read-back."""
    if isinstance(payload, dict):
        return {
            key: normalized_iam_document(value)
            for key, value in sorted(payload.items())
        }
    if isinstance(payload, list):
        normalized = [normalized_iam_document(value) for value in payload]
        return sorted(normalized, key=canonical_json)
    return payload


def iam_documents_equal(actual: Any, expected: Any) -> bool:
    return normalized_iam_document(actual) == normalized_iam_document(expected)


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        relative = path.relative_to(REPOSITORY_ROOT).as_posix()
        raise RuntimeError(f"JSON contract must be an object: {relative}")
    return payload


def contract_file(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if CONTRACT_PARENT.resolve() not in path.parents:
        raise RuntimeError("Static IAM document escaped the contract root")
    return path


def contract_paths(root: Path, manifest: dict[str, Any]) -> list[Path]:
    documents = {
        *(spec["document"] for spec in manifest["managedPolicies"].values()),
        *(spec["trust"] for spec in manifest["roles"].values()),
    }
    return [
        root / "manifest.json",
        *(contract_file(root, name) for name in sorted(documents)),
    ]


def expected_digests(root: Path, manifest: dict[str, Any]) -> dict[str, str]:
    return {
        path.resolve().relative_to(CONTRACT_PARENT.resolve()).as_posix(): sha256(
            load_json(path)
        )
        for path in contract_paths(root, manifest)
    }


def write_digests() -> None:
    for root in CONTRACT_ROOTS.values():
        manifest = load_json(root / "manifest.json")
        payload = {
            "schemaVersion": 2,
            "canonicalization": "RFC8259 JSON; UTF-8; sorted keys; compact separators",
            "documents": expected_digests(root, manifest),
        }
        (root / "static-contract-digests.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )


def render_tokens(
    *,
    account_id: str,
    partition: str,
    region: str,
    environment: str,
    name_prefix: str,
    repository_identity: str,
    state_bucket_name: str,
    github_repository_subject: str | None = None,
) -> dict[str, str]:
    repository_subject = github_repository_subject or f"repo:{repository_identity}"
    return {
        "AWS_ACCOUNT_ID": account_id,
        "AWS_PARTITION": partition,
        "AWS_REGION": region,
        "ENVIRONMENT": environment,
        "NAME_PREFIX": name_prefix,
        "REPOSITORY_IDENTITY": repository_identity,
        "STATE_BUCKET_NAME": state_bucket_name,
        "GITHUB_REPOSITORY_SUBJECT": repository_subject,
        "GITHUB_ENVIRONMENT": "aws-deployment",
        "GITHUB_WORKFLOW_NAME": "Deploy managed AWS proof",
        "GITHUB_WORKFLOW_REF": (
            f"{repository_identity}/.github/workflows/aws-deploy.yml@refs/heads/main"
        ),
    }


def rendered(payload: Any, tokens: dict[str, str]) -> Any:
    text = json.dumps(payload)
    for key, value in tokens.items():
        text = text.replace(f"${{{key}}}", value)
    if "${" in text:
        raise RuntimeError("Static IAM contract contains an unresolved token")
    return json.loads(text)


def canonical_role_tags(
    manifest: dict[str, Any], purpose: str, tokens: dict[str, str]
) -> dict[str, str]:
    role_tags = manifest["roles"][purpose].get("tags")
    if not isinstance(role_tags, dict):
        raise RuntimeError(f"Static role tag contract is missing: {purpose}")
    expected = {
        **rendered(manifest["ownershipTags"], tokens),
        "PortfolioPurpose": purpose.replace("_", "-"),
    }
    if purpose == "automation":
        expected["PortfolioEnvironment"] = "shared"
    actual = rendered(role_tags, tokens)
    if actual != expected:
        raise RuntimeError(f"Static role tag contract drifted: {purpose}")
    return expected


def verify_exact_role_tags(
    purpose: str, expected: dict[str, str], actual: dict[str, str]
) -> None:
    if actual != expected:
        raise RuntimeError(f"Static role tags drifted: {purpose}")


def statement_by_sid(policy: dict[str, Any], sid: str) -> dict[str, Any]:
    statements = [item for item in policy["Statement"] if item.get("Sid") == sid]
    if len(statements) != 1:
        raise RuntimeError(f"Expected one static IAM statement: {sid}")
    return statements[0]


def verify_contract_payloads(
    root: Path,
    environment: str,
    manifest: dict[str, Any],
    policy: dict[str, Any],
    boundary: dict[str, Any],
    digest_contract: dict[str, Any],
    calculated: dict[str, str],
) -> dict[str, int]:
    if manifest.get("schemaVersion") != 2:
        raise RuntimeError("Unknown static IAM manifest schema")
    expected_lifecycle = {
        "staticIamOwner": "owner-admin principal",
        "deploymentMode": "read-only-consumer",
        "deploymentIamMutation": False,
        "deploymentPolicyGeneration": False,
        "deploymentQuotaCalculation": False,
        "driftMode": "fail-closed",
    }
    if manifest.get("lifecycle") != expected_lifecycle:
        raise RuntimeError("Persistent static IAM lifecycle contract drifted")

    policy_specs = manifest.get("managedPolicies", {})
    if "staticIamAttestation" not in policy_specs:
        raise RuntimeError("Static IAM attestation policy is missing")
    operator = manifest["roles"]["operator_deployment"]
    expected_operator_policies = [
        "operatorPermissions",
        "staticIamAttestation",
        "managedEnvironmentPermissions",
        "managedEnvironmentResourcePermissions",
        "lifecycleControl",
    ]
    if operator.get("permissions") != expected_operator_policies:
        raise RuntimeError("Operator static policy attachments drifted")
    if set(manifest.get("roles", {})) != {
        "automation",
        "operator_deployment",
        "task_execution",
        "web_workload",
        "api_workload",
        "ml_workload",
        "destroy",
        "scheduler",
        "codebuild_image",
        "codebuild_destroy",
    }:
        raise RuntimeError("Static IAM role inventory must include exact automation")
    if not {"automation", "automationBoundary"}.issubset(policy_specs):
        raise RuntimeError("Static IAM automation policies are missing")

    tokens = render_tokens(
        account_id="111122223333",
        partition="aws",
        region="us-east-1",
        environment=environment,
        name_prefix="example-portfolio",
        repository_identity="example-owner/example-repository",
        state_bucket_name="example-portfolio-111122223333-us-east-1-state",
    )
    for purpose in manifest["roles"]:
        canonical_role_tags(manifest, purpose, tokens)
    automation_policy = rendered(
        load_json(contract_file(root, policy_specs["automation"]["document"])),
        tokens,
    )
    automation_boundary = rendered(
        load_json(contract_file(root, policy_specs["automationBoundary"]["document"])),
        tokens,
    )
    automation_resources = set(
        values(
            statement_by_sid(
                automation_policy, "AssumeExactManualAndMonthlyLifecycleRoles"
            )["Resource"]
        )
    )
    boundary_resources = set(
        values(
            statement_by_sid(automation_boundary, "ExactAutomationAssumeRoleCeiling")[
                "Resource"
            ]
        )
    )
    expected_automation_resources = {
        f"arn:aws:iam::111122223333:role/example-portfolio-{mode}-{purpose}"
        for mode in ("manual", "monthly")
        for purpose in ("operator-deployment", "destroy")
    }
    if (
        automation_resources != expected_automation_resources
        or boundary_resources != expected_automation_resources
    ):
        raise RuntimeError("Automation authority is not the exact four lifecycle roles")
    automation_trust = rendered(
        load_json(contract_file(root, manifest["roles"]["automation"]["trust"])),
        tokens,
    )
    trust_statement = statement_by_sid(
        automation_trust, "ExactGitHubDeploymentWorkflow"
    )
    trust_equals = trust_statement.get("Condition", {}).get("StringEquals", {})
    expected_subjects = {
        "repo:example-owner/example-repository:environment:aws-deployment:"
        "job_workflow_ref:example-owner/example-repository/.github/workflows/"
        f"aws-deploy.yml@refs/heads/main:event_name:{event}"
        for event in ("schedule", "workflow_dispatch")
    }
    if (
        trust_statement.get("Action") != "sts:AssumeRoleWithWebIdentity"
        or set(values(trust_equals.get("token.actions.githubusercontent.com:sub", [])))
        != expected_subjects
        or trust_equals.get("token.actions.githubusercontent.com:aud")
        != "sts.amazonaws.com"
        or trust_equals.get("token.actions.githubusercontent.com:repository")
        != "example-owner/example-repository"
        or trust_equals.get("token.actions.githubusercontent.com:ref")
        != "refs/heads/main"
        or trust_equals.get("token.actions.githubusercontent.com:environment")
        != "aws-deployment"
    ):
        raise RuntimeError("Automation OIDC trust boundary drifted")
    operator_trust = rendered(
        load_json(
            contract_file(root, manifest["roles"]["operator_deployment"]["trust"])
        ),
        tokens,
    )
    operator_principals = set(
        values(operator_trust["Statement"][0]["Principal"]["AWS"])
    )
    if operator_principals != {
        "arn:aws:iam::111122223333:user/ReactorFrontNoel",
        "arn:aws:iam::111122223333:role/example-portfolio-automation",
    }:
        raise RuntimeError("Operator target trust is not exact")
    statements = {
        "ReadExactDeploymentSourceIdentity": USER_READ_ACTIONS,
        "ReadExactPersistentRoles": ROLE_READ_ACTIONS,
        "ReadExactPersistentManagedPolicies": POLICY_READ_ACTIONS,
    }
    for sid, expected_actions in statements.items():
        statement = statement_by_sid(policy, sid)
        if (
            statement.get("Effect") != "Allow"
            or set(values(statement["Action"])) != expected_actions
        ):
            raise RuntimeError(f"Static IAM read actions drifted: {sid}")
        if "*" in values(statement["Resource"]):
            raise RuntimeError(f"Static IAM read scope must use exact ARNs: {sid}")

    all_actions = {
        action
        for statement in policy["Statement"]
        for action in values(statement["Action"])
    }
    mutations = sorted(
        action
        for action in all_actions
        if action.split(":", 1)[1].lower().startswith(MUTATION_PREFIXES)
    )
    if mutations:
        raise RuntimeError(
            f"Static IAM attestation contains mutation actions: {mutations}"
        )

    ceiling = statement_by_sid(boundary, "StaticIamAttestationCeiling")
    if (
        set(values(ceiling["Action"]))
        != USER_READ_ACTIONS | ROLE_READ_ACTIONS | POLICY_READ_ACTIONS
    ):
        raise RuntimeError("Static IAM boundary read ceiling drifted")
    identity_resources = {
        resource
        for statement in policy["Statement"]
        for resource in values(statement["Resource"])
    }
    expected_ceiling_resources = {
        "arn:aws:iam::111122223333:user/ReactorFrontNoel",
        "arn:aws:iam::111122223333:role/example-portfolio-automation",
        f"arn:aws:iam::111122223333:role/example-portfolio-{environment}-*",
        "arn:aws:iam::111122223333:policy/ReactorFrontPortfolio*",
    }
    if set(values(ceiling["Resource"])) != expected_ceiling_resources:
        raise RuntimeError("Static IAM boundary read ceiling drifted")

    expected_role_arns = {
        f"arn:aws:iam::111122223333:role/{spec['name']}"
        for spec in rendered(manifest, tokens)["roles"].values()
    }
    expected_policy_arns = {
        f"arn:aws:iam::111122223333:policy/{spec['name']}"
        for spec in manifest["managedPolicies"].values()
    }
    expected_user_arn = "arn:aws:iam::111122223333:user/ReactorFrontNoel"
    if identity_resources != expected_role_arns | expected_policy_arns | {
        expected_user_arn
    }:
        raise RuntimeError("Static IAM attestation inventory is not exact")

    if digest_contract.get("schemaVersion") != 2:
        raise RuntimeError("Unknown static IAM digest schema")
    if digest_contract.get("documents") != calculated:
        raise RuntimeError("Static IAM canonical digests drifted")

    forbidden_actions = {
        "iam:AttachRolePolicy",
        "iam:CreatePolicyVersion",
        "iam:DeletePolicyVersion",
        "iam:DetachRolePolicy",
        "iam:PutRolePolicy",
        "iam:SetDefaultPolicyVersion",
        "iam:UpdateAssumeRolePolicy",
    }
    if all_actions & forbidden_actions:
        raise RuntimeError("Static attestation unexpectedly repairs IAM")
    return {
        "readActions": len(all_actions),
        "exactResources": len(identity_resources),
    }


def expect_rejection(label: str, operation: Any) -> None:
    try:
        operation()
    except RuntimeError:
        return
    raise RuntimeError(f"Static IAM fail-closed mutation was accepted: {label}")


def verify_mutation_boundaries(
    root: Path,
    environment: str,
    manifest: dict[str, Any],
    policy: dict[str, Any],
    boundary: dict[str, Any],
    digest_contract: dict[str, Any],
    calculated: dict[str, str],
) -> int:
    cases: list[
        tuple[str, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]
    ] = []

    mutable_manifest = copy.deepcopy(manifest)
    mutable_manifest["lifecycle"]["deploymentIamMutation"] = True
    cases.append(
        ("deployment IAM mutation", mutable_manifest, policy, boundary, digest_contract)
    )

    mutable_policy = copy.deepcopy(policy)
    mutable_policy["Statement"][0]["Action"].append("iam:CreatePolicyVersion")
    cases.append(
        ("IAM write action", manifest, mutable_policy, boundary, digest_contract)
    )

    wildcard_policy = copy.deepcopy(policy)
    wildcard_policy["Statement"][0]["Resource"] = "*"
    cases.append(
        ("wildcard IAM target", manifest, wildcard_policy, boundary, digest_contract)
    )

    narrow_boundary = copy.deepcopy(boundary)
    ceiling = statement_by_sid(narrow_boundary, "StaticIamAttestationCeiling")
    ceiling["Action"].remove("iam:GetPolicyVersion")
    cases.append(
        ("missing boundary read", manifest, policy, narrow_boundary, digest_contract)
    )

    stale_digests = copy.deepcopy(digest_contract)
    manifest_key = (
        (root / "manifest.json")
        .resolve()
        .relative_to(CONTRACT_PARENT.resolve())
        .as_posix()
    )
    stale_digests["documents"][manifest_key] = "0" * 64
    cases.append(("stale canonical digest", manifest, policy, boundary, stale_digests))

    tokens = render_tokens(
        account_id="111122223333",
        partition="aws",
        region="us-east-1",
        environment=environment,
        name_prefix="example-portfolio",
        repository_identity="example-owner/example-repository",
        state_bucket_name="example-portfolio-111122223333-us-east-1-state",
    )
    tag_cases: list[tuple[str, str, dict[str, str], dict[str, str]]] = []
    purposes = tuple(manifest["roles"])
    for purpose in purposes:
        expected_tags = canonical_role_tags(manifest, purpose, tokens)

        missing_tag = copy.deepcopy(expected_tags)
        missing_tag.pop("PortfolioPurpose")
        tag_cases.append(
            (
                f"missing role purpose tag: {purpose}",
                purpose,
                expected_tags,
                missing_tag,
            )
        )

        wrong_tag = copy.deepcopy(expected_tags)
        wrong_tag["PortfolioPurpose"] = next(
            candidate.replace("_", "-")
            for candidate in purposes
            if candidate != purpose
        )
        tag_cases.append(
            (f"wrong role purpose tag: {purpose}", purpose, expected_tags, wrong_tag)
        )

        extra_tag = copy.deepcopy(expected_tags)
        extra_tag["UndeclaredTag"] = "unexpected"
        tag_cases.append(
            (f"extra role tag: {purpose}", purpose, expected_tags, extra_tag)
        )

    for label, case_manifest, case_policy, case_boundary, case_digests in cases:
        expect_rejection(
            label,
            lambda m=case_manifest, p=case_policy, b=case_boundary, d=case_digests: (
                verify_contract_payloads(root, environment, m, p, b, d, calculated)
            ),
        )
    for label, purpose, expected_tags, actual_tags in tag_cases:
        expect_rejection(
            label,
            lambda p=purpose, e=expected_tags, a=actual_tags: verify_exact_role_tags(
                p, e, a
            ),
        )
    return len(cases) + len(tag_cases)


def verify_live_document_normalization() -> int:
    expected = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["sts:TagSession", "sts:AssumeRole"],
                "Principal": {
                    "AWS": ["arn:example:role/operator", "arn:example:role/controller"]
                },
            }
        ],
    }
    reordered = copy.deepcopy(expected)
    reordered["Statement"][0]["Action"].reverse()
    reordered["Statement"][0]["Principal"]["AWS"].reverse()
    if not iam_documents_equal(reordered, expected):
        raise RuntimeError("IAM live document normalization rejected reordered sets")

    missing = copy.deepcopy(expected)
    missing["Statement"][0]["Principal"]["AWS"].pop()
    if iam_documents_equal(missing, expected):
        raise RuntimeError(
            "IAM live document normalization accepted a missing principal"
        )

    changed = copy.deepcopy(expected)
    changed["Statement"][0]["Effect"] = "Deny"
    if iam_documents_equal(changed, expected):
        raise RuntimeError("IAM live document normalization accepted changed semantics")
    return 3


def verify_offline() -> dict[str, Any]:
    profiles: dict[str, dict[str, Any]] = {}
    calculated_profiles: dict[str, dict[str, str]] = {}
    for environment, root in CONTRACT_ROOTS.items():
        manifest = load_json(root / "manifest.json")
        policy_specs = manifest.get("managedPolicies", {})
        tokens = render_tokens(
            account_id="111122223333",
            partition="aws",
            region="us-east-1",
            environment=environment,
            name_prefix="example-portfolio",
            repository_identity="example-owner/example-repository",
            state_bucket_name="example-portfolio-111122223333-us-east-1-state",
        )
        policy = rendered(
            load_json(
                contract_file(root, policy_specs["staticIamAttestation"]["document"])
            ),
            tokens,
        )
        boundary = rendered(
            load_json(
                contract_file(root, policy_specs["operatorBoundary"]["document"])
            ),
            tokens,
        )
        digest_contract = load_json(root / "static-contract-digests.json")
        calculated = expected_digests(root, manifest)
        result = verify_contract_payloads(
            root,
            environment,
            manifest,
            policy,
            boundary,
            digest_contract,
            calculated,
        )
        mutation_cases = verify_mutation_boundaries(
            root,
            environment,
            manifest,
            policy,
            boundary,
            digest_contract,
            calculated,
        )
        profiles[environment] = {
            "managedPolicies": len(policy_specs),
            "roles": len(manifest["roles"]),
            "sourceUsers": len(manifest["sourceUsers"]),
            **result,
            "canonicalDocuments": len(calculated),
            "failClosedMutationCases": mutation_cases,
        }
        calculated_profiles[environment] = calculated
    normalization_cases = verify_live_document_normalization()
    return {
        "schemaVersion": 3,
        "environmentProfiles": profiles,
        "canonicalContractSha256": sha256(calculated_profiles),
        "liveDocumentNormalizationCases": normalization_cases,
        "staticVerifierAwsApiCalls": 0,
        "staticVerifierAwsWrites": 0,
        "staticVerifierAwsResourcesCreated": 0,
        "liveAwsHistoryIncluded": False,
    }


class AwsCli:
    def __init__(self, executable: str, env: dict[str, str] | None = None) -> None:
        self.executable = executable
        self.env = env
        self.calls = 0

    def call(
        self, *arguments: str, allow_missing_login: bool = False
    ) -> dict[str, Any] | None:
        self.calls += 1
        result = subprocess.run(
            [self.executable, *arguments, "--output", "json", "--no-cli-pager"],
            cwd=REPOSITORY_ROOT,
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            if allow_missing_login and "NoSuchEntity" in result.stderr:
                return None
            raise RuntimeError(
                f"Read-only AWS attestation call failed: {arguments[0]} {arguments[1]}"
            )
        payload = json.loads(result.stdout or "{}")
        if not isinstance(payload, dict):
            raise RuntimeError("AWS CLI returned a non-object response")
        return payload


def arn_set(items: list[dict[str, Any]], key: str) -> set[str]:
    return {str(item[key]) for item in items}


def verify_live(args: argparse.Namespace) -> dict[str, Any]:
    offline = verify_offline()
    root = CONTRACT_ROOTS[args.environment]
    manifest_template = load_json(root / "manifest.json")
    tokens = render_tokens(
        account_id=args.account_id,
        partition=args.partition,
        region=args.region,
        environment=args.environment,
        name_prefix=args.name_prefix,
        repository_identity=args.repository_identity,
        state_bucket_name=args.state_bucket_name,
    )
    manifest = rendered(manifest_template, tokens)
    source_spec = manifest["sourceUsers"]["noel_deployment"]
    source_arn = (
        f"arn:{args.partition}:iam::{args.account_id}:user/{source_spec['name']}"
    )
    role_specs = manifest["roles"]
    role_arns = {
        key: f"arn:{args.partition}:iam::{args.account_id}:role/{spec['name']}"
        for key, spec in role_specs.items()
    }
    policy_specs = manifest["managedPolicies"]
    policy_arns = {
        key: f"arn:{args.partition}:iam::{args.account_id}:policy/{spec['name']}"
        for key, spec in policy_specs.items()
    }

    source = AwsCli(args.aws_cli)
    identity = source.call("sts", "get-caller-identity") or {}
    identity_arn = str(identity.get("Arn", ""))
    if args.caller_mode == "source-user":
        caller_verified = identity_arn == source_arn
    else:
        caller_verified = (
            re.fullmatch(
                rf"arn:{re.escape(args.partition)}:sts::{re.escape(args.account_id)}:"
                rf"assumed-role/{re.escape(args.name_prefix)}-automation/"
                r"portfolio-github-[0-9]+",
                identity_arn,
            )
            is not None
        )
    if not caller_verified:
        raise RuntimeError("Active credential is not the exact lifecycle caller")
    assumed = (
        source.call(
            "sts",
            "assume-role",
            "--role-arn",
            role_arns["operator_deployment"],
            "--role-session-name",
            "portfolio-static-iam-attestation",
            "--duration-seconds",
            "900",
        )
        or {}
    )
    credentials = assumed.get("Credentials", {})
    required = {"AccessKeyId", "SecretAccessKey", "SessionToken"}
    if not required.issubset(credentials):
        raise RuntimeError(
            "AssumeRole did not return a complete temporary credential set"
        )
    session_env = dict(os.environ)
    session_env.update(
        {
            "AWS_ACCESS_KEY_ID": credentials["AccessKeyId"],
            "AWS_SECRET_ACCESS_KEY": credentials["SecretAccessKey"],
            "AWS_SESSION_TOKEN": credentials["SessionToken"],
            "AWS_DEFAULT_REGION": args.region,
        }
    )
    operator = AwsCli(args.aws_cli, session_env)
    operator_identity = operator.call("sts", "get-caller-identity") or {}
    expected_session_prefix = (
        f"arn:{args.partition}:sts::{args.account_id}:assumed-role/"
        f"{role_specs['operator_deployment']['name']}/"
    )
    if not str(operator_identity.get("Arn", "")).startswith(expected_session_prefix):
        raise RuntimeError("Temporary credential is not the exact operator session")

    user = operator.call("iam", "get-user", "--user-name", source_spec["name"]) or {}
    if user.get("User", {}).get("Arn") != source_arn or user.get("User", {}).get(
        "PermissionsBoundary"
    ):
        raise RuntimeError("Deployment source user identity or boundary drifted")
    attached_user = (
        operator.call(
            "iam", "list-attached-user-policies", "--user-name", source_spec["name"]
        )
        or {}
    )
    expected_user_policies = {policy_arns[key] for key in source_spec["permissions"]}
    if (
        arn_set(attached_user.get("AttachedPolicies", []), "PolicyArn")
        != expected_user_policies
    ):
        raise RuntimeError("Deployment source user attachments drifted")
    for operation, key in (
        ("list-user-policies", "PolicyNames"),
        ("list-groups-for-user", "Groups"),
    ):
        payload = (
            operator.call("iam", operation, "--user-name", source_spec["name"]) or {}
        )
        if payload.get(key):
            raise RuntimeError(f"Deployment source user {operation} must be empty")
    login = operator.call(
        "iam",
        "get-login-profile",
        "--user-name",
        source_spec["name"],
        allow_missing_login=True,
    )
    if login is not None:
        raise RuntimeError("Deployment source user unexpectedly has Console login")
    keys = (
        operator.call("iam", "list-access-keys", "--user-name", source_spec["name"])
        or {}
    )
    statuses = [item.get("Status") for item in keys.get("AccessKeyMetadata", [])]
    if statuses != ["Active"]:
        raise RuntimeError(
            "Deployment source user must have exactly one active access key"
        )

    for purpose, spec in role_specs.items():
        role = operator.call("iam", "get-role", "--role-name", spec["name"]) or {}
        role_value = role.get("Role", {})
        expected_trust = rendered(load_json(contract_file(root, spec["trust"])), tokens)
        if role_value.get("Arn") != role_arns[purpose]:
            raise RuntimeError(f"Static role ARN drifted: {purpose}")
        if not iam_documents_equal(
            role_value.get("AssumeRolePolicyDocument"), expected_trust
        ):
            raise RuntimeError(f"Static role trust drifted: {purpose}")
        if (
            role_value.get("PermissionsBoundary", {}).get("PermissionsBoundaryArn")
            != policy_arns[spec["boundary"]]
        ):
            raise RuntimeError(f"Static role boundary drifted: {purpose}")
        attached = (
            operator.call(
                "iam", "list-attached-role-policies", "--role-name", spec["name"]
            )
            or {}
        )
        expected = {policy_arns[key] for key in spec["permissions"]}
        if arn_set(attached.get("AttachedPolicies", []), "PolicyArn") != expected:
            raise RuntimeError(f"Static role attachments drifted: {purpose}")
        inline = (
            operator.call("iam", "list-role-policies", "--role-name", spec["name"])
            or {}
        )
        if inline.get("PolicyNames"):
            raise RuntimeError(f"Static role has an inline policy: {purpose}")
        tags = operator.call("iam", "list-role-tags", "--role-name", spec["name"]) or {}
        tag_map = {item["Key"]: item["Value"] for item in tags.get("Tags", [])}
        expected_tags = canonical_role_tags(manifest, purpose, tokens)
        verify_exact_role_tags(purpose, expected_tags, tag_map)

    for key, spec in policy_specs.items():
        metadata = (
            operator.call("iam", "get-policy", "--policy-arn", policy_arns[key]) or {}
        )
        policy_value = metadata.get("Policy", {})
        if policy_value.get("Arn") != policy_arns[key]:
            raise RuntimeError(f"Static managed policy ARN drifted: {key}")
        version_id = str(policy_value.get("DefaultVersionId", ""))
        version = (
            operator.call(
                "iam",
                "get-policy-version",
                "--policy-arn",
                policy_arns[key],
                "--version-id",
                version_id,
            )
            or {}
        )
        expected_document = rendered(
            load_json(contract_file(root, spec["document"])), tokens
        )
        if not iam_documents_equal(
            version.get("PolicyVersion", {}).get("Document"), expected_document
        ):
            raise RuntimeError(f"Static managed policy document drifted: {key}")
        operator.call("iam", "list-policy-versions", "--policy-arn", policy_arns[key])
        operator.call("iam", "list-policy-tags", "--policy-arn", policy_arns[key])
        permission_entities = (
            operator.call(
                "iam",
                "list-entities-for-policy",
                "--policy-arn",
                policy_arns[key],
                "--policy-usage-filter",
                "PermissionsPolicy",
            )
            or {}
        )
        boundary_entities = (
            operator.call(
                "iam",
                "list-entities-for-policy",
                "--policy-arn",
                policy_arns[key],
                "--policy-usage-filter",
                "PermissionsBoundary",
            )
            or {}
        )
        expected_permission_users = (
            {source_spec["name"]} if key in source_spec["permissions"] else set()
        )
        expected_permission_roles = {
            role_spec["name"]
            for role_spec in role_specs.values()
            if key in role_spec["permissions"]
        }
        actual_permission_users = {
            item["UserName"] for item in permission_entities.get("PolicyUsers", [])
        }
        actual_permission_roles = {
            item["RoleName"] for item in permission_entities.get("PolicyRoles", [])
        }
        if (
            actual_permission_users != expected_permission_users
            or actual_permission_roles != expected_permission_roles
            or permission_entities.get("PolicyGroups")
        ):
            raise RuntimeError(f"Static managed policy attachments drifted: {key}")
        if key == "operatorBoundary":
            expected_boundary_roles = {
                role_spec["name"]
                for purpose, role_spec in role_specs.items()
                if purpose != "automation"
            }
        elif key == "automationBoundary":
            expected_boundary_roles = {role_specs["automation"]["name"]}
        else:
            expected_boundary_roles = set()
        actual_boundary_roles = {
            item["RoleName"] for item in boundary_entities.get("PolicyRoles", [])
        }
        if (
            actual_boundary_roles != expected_boundary_roles
            or boundary_entities.get("PolicyUsers")
            or boundary_entities.get("PolicyGroups")
        ):
            raise RuntimeError(f"Static managed policy boundary usages drifted: {key}")

    live_shape = {
        "sourceUser": source_spec["name"],
        "sourcePolicyArns": sorted(expected_user_policies),
        "roleArns": sorted(role_arns.values()),
        "policyArns": sorted(policy_arns.values()),
    }
    return {
        **offline,
        "mode": "live-read-only",
        "callerMode": args.caller_mode,
        "sourceCredentialVerified": args.caller_mode == "source-user",
        "automationCredentialVerified": args.caller_mode == "github-automation",
        "operatorSessionVerified": True,
        "drift": False,
        "attestationAwsReadCalls": source.calls + operator.calls,
        "attestationAwsWriteCalls": 0,
        "attestationAwsResourcesCreated": 0,
        "renderedInventorySha256": sha256(live_shape),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify the frozen persistent deployment IAM contract"
    )
    parser.add_argument("--write-digests", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--aws-cli", default="aws")
    parser.add_argument(
        "--caller-mode",
        choices=("source-user", "github-automation"),
        default="source-user",
    )
    for name in (
        "account-id",
        "partition",
        "region",
        "name-prefix",
        "environment",
        "repository-identity",
        "state-bucket-name",
    ):
        parser.add_argument(f"--{name}")
    args = parser.parse_args()
    if args.live:
        missing = [
            name
            for name in (
                "account_id",
                "partition",
                "region",
                "name_prefix",
                "environment",
                "repository_identity",
                "state_bucket_name",
            )
            if not getattr(args, name)
        ]
        if missing:
            parser.error(f"--live requires explicit inputs: {', '.join(missing)}")
        if args.environment not in CONTRACT_ROOTS:
            parser.error("--environment must be manual or monthly")
    return args


def main() -> int:
    args = parse_args()
    if args.write_digests:
        if args.live:
            raise RuntimeError(
                "Digest maintenance and live attestation are separate operations"
            )
        write_digests()
    result = verify_live(args) if args.live else verify_offline()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (json.JSONDecodeError, OSError, RuntimeError) as error:
        print(f"Static IAM verification failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
