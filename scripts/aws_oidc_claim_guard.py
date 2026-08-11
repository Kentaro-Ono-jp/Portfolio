from __future__ import annotations

import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

EXPECTED_REPOSITORY = "Kentaro-Ono-jp/Portfolio"
EXPECTED_REF = "refs/heads/main"
EXPECTED_ENVIRONMENT = "aws-deployment"
EXPECTED_WORKFLOW = "Deploy managed AWS proof"
EXPECTED_WORKFLOW_REF = (
    "Kentaro-Ono-jp/Portfolio/.github/workflows/aws-deploy.yml@refs/heads/main"
)
EXPECTED_EVENTS = {"workflow_dispatch", "schedule"}


def expected_claims(event_name: str) -> dict[str, str]:
    if event_name not in EXPECTED_EVENTS:
        raise RuntimeError("OIDC event claim is not accepted")
    subject = (
        f"repo:{EXPECTED_REPOSITORY}:environment:{EXPECTED_ENVIRONMENT}:"
        f"job_workflow_ref:{EXPECTED_WORKFLOW_REF}:event_name:{event_name}"
    )
    return {
        "aud": "sts.amazonaws.com",
        "sub": subject,
        "repository": EXPECTED_REPOSITORY,
        "ref": EXPECTED_REF,
        "environment": EXPECTED_ENVIRONMENT,
        "job_workflow_ref": EXPECTED_WORKFLOW_REF,
        "workflow": EXPECTED_WORKFLOW,
        "event_name": event_name,
    }


def decode_claims(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise RuntimeError("GitHub OIDC token shape is invalid")
    encoded = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError("GitHub OIDC claim payload is invalid") from error
    if not isinstance(payload, dict):
        raise TypeError("GitHub OIDC claim payload is not an object")
    return payload


def validate_claims(claims: Mapping[str, Any], event_name: str) -> None:
    for key, expected in expected_claims(event_name).items():
        actual = claims.get(key)
        if actual != expected:
            raise RuntimeError(
                f"OIDC claim mismatch: {key} expected={expected!r} actual={actual!r}"
            )


def request_token(values: Mapping[str, str]) -> str:
    request_url = values.get("ACTIONS_ID_TOKEN_REQUEST_URL", "")
    request_token = values.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
    if not request_url or not request_token:
        raise RuntimeError("GitHub OIDC request surface is unavailable")
    separator = "&" if "?" in request_url else "?"
    url = (
        request_url
        + separator
        + urllib.parse.urlencode({"audience": "sts.amazonaws.com"})
    )
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"bearer {request_token}",
            "Accept": "application/json; api-version=2.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError("GitHub OIDC token request failed safely") from error
    token = payload.get("value") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise RuntimeError("GitHub OIDC token response is invalid")
    return token


def append_summary(path: str, event_name: str) -> None:
    with Path(path).open("a", encoding="utf-8", newline="\n") as target:
        target.write(
            "## GitHub OIDC claim guard\n\n"
            "- Audience: `sts.amazonaws.com`\n"
            f"- Event: `{event_name}`\n"
            "- Repository/ref/environment/workflow subject: exact\n"
        )


def main() -> int:
    try:
        event_name = os.environ.get("GITHUB_EVENT_NAME", "")
        token = request_token(os.environ)
        validate_claims(decode_claims(token), event_name)
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")
        if not summary_path:
            raise RuntimeError("GitHub summary surface is unavailable")
        append_summary(summary_path, event_name)
        return 0
    except (RuntimeError, TypeError) as error:
        print(f"OIDC claim guard failed safely: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
