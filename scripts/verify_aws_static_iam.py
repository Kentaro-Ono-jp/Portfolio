from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = REPOSITORY_ROOT / "infra" / "aws" / "environment" / "console-iam"
DIGEST_PATH = CONTRACT_ROOT / "static-contract-digests.json"
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


def contract_paths(manifest: dict[str, Any]) -> list[Path]:
    documents = {
        "manifest.json",
        *(spec["document"] for spec in manifest["managedPolicies"].values()),
        *(spec["trust"] for spec in manifest["roles"].values()),
    }
    return [CONTRACT_ROOT / name for name in sorted(documents)]


def expected_digests(manifest: dict[str, Any]) -> dict[str, str]:
    return {path.name: sha256(load_json(path)) for path in contract_paths(manifest)}


def write_digests() -> None:
    manifest = load_json(CONTRACT_ROOT / "manifest.json")
    payload = {
        "schemaVersion": 1,
        "canonicalization": "RFC8259 JSON; UTF-8; sorted keys; compact separators",
        "documents": expected_digests(manifest),
    }
    DIGEST_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


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

    tokens = {
        "AWS_ACCOUNT_ID": "111122223333",
        "AWS_PARTITION": "aws",
        "AWS_REGION": "us-east-1",
        "ENVIRONMENT": "manual",
        "NAME_PREFIX": "example-portfolio",
        "REPOSITORY_IDENTITY": "example-owner/example-repository",
        "STATE_BUCKET_NAME": "example-portfolio-111122223333-us-east-1-state",
    }
    for purpose in manifest["roles"]:
        canonical_role_tags(manifest, purpose, tokens)
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
        "arn:aws:iam::111122223333:role/example-portfolio-manual-*",
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

    if digest_contract.get("schemaVersion") != 1:
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
    stale_digests["documents"]["manifest.json"] = "0" * 64
    cases.append(("stale canonical digest", manifest, policy, boundary, stale_digests))

    tokens = {
        "AWS_ACCOUNT_ID": "111122223333",
        "AWS_PARTITION": "aws",
        "AWS_REGION": "us-east-1",
        "ENVIRONMENT": "manual",
        "NAME_PREFIX": "example-portfolio",
        "REPOSITORY_IDENTITY": "example-owner/example-repository",
        "STATE_BUCKET_NAME": "example-portfolio-111122223333-us-east-1-state",
    }
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
                verify_contract_payloads(m, p, b, d, calculated)
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
    manifest = load_json(CONTRACT_ROOT / "manifest.json")
    policy_specs = manifest.get("managedPolicies", {})
    tokens = {
        "AWS_ACCOUNT_ID": "111122223333",
        "AWS_PARTITION": "aws",
        "AWS_REGION": "us-east-1",
        "ENVIRONMENT": "manual",
        "NAME_PREFIX": "example-portfolio",
        "REPOSITORY_IDENTITY": "example-owner/example-repository",
        "STATE_BUCKET_NAME": "example-portfolio-111122223333-us-east-1-state",
    }
    policy = rendered(
        load_json(CONTRACT_ROOT / policy_specs["staticIamAttestation"]["document"]),
        tokens,
    )
    boundary = rendered(
        load_json(CONTRACT_ROOT / policy_specs["operatorBoundary"]["document"]),
        tokens,
    )
    digest_contract = load_json(DIGEST_PATH)
    calculated = expected_digests(manifest)
    result = verify_contract_payloads(
        manifest, policy, boundary, digest_contract, calculated
    )
    mutation_cases = verify_mutation_boundaries(
        manifest, policy, boundary, digest_contract, calculated
    )
    normalization_cases = verify_live_document_normalization()
    return {
        "schemaVersion": manifest["schemaVersion"],
        "managedPolicies": len(policy_specs),
        "roles": len(manifest["roles"]),
        "sourceUsers": len(manifest["sourceUsers"]),
        **result,
        "canonicalDocuments": len(calculated),
        "canonicalContractSha256": sha256(calculated),
        "failClosedMutationCases": mutation_cases,
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
    manifest_template = load_json(CONTRACT_ROOT / "manifest.json")
    tokens = {
        "AWS_ACCOUNT_ID": args.account_id,
        "AWS_PARTITION": args.partition,
        "AWS_REGION": args.region,
        "ENVIRONMENT": args.environment,
        "NAME_PREFIX": args.name_prefix,
        "REPOSITORY_IDENTITY": args.repository_identity,
        "STATE_BUCKET_NAME": args.state_bucket_name,
    }
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
    if identity.get("Arn") != source_arn:
        raise RuntimeError("Active source credential is not the exact deployment user")
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
        expected_trust = rendered(load_json(CONTRACT_ROOT / spec["trust"]), tokens)
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
            load_json(CONTRACT_ROOT / spec["document"]), tokens
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
        expected_boundary_roles = (
            {role_spec["name"] for role_spec in role_specs.values()}
            if key == "operatorBoundary"
            else set()
        )
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
        "sourceCredentialVerified": True,
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
