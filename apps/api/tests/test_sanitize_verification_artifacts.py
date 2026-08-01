from __future__ import annotations

import json
import zipfile
from pathlib import Path

from scripts import sanitize_verification_artifacts as sanitizer

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_artifact_scan_accepts_sanitized_evidence(tmp_path: Path) -> None:
    (tmp_path / "result.json").write_text(
        json.dumps(
            {
                "status": "approved",
                "correlationId": "11111111-1111-4111-8111-111111111111",
                "tokenPersisted": False,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pytest.xml").write_text(
        '<testsuite><testcase name="rejects -----BEGIN PRIVATE KEY-----" />'
        '<testcase name="failed"><failure>sanitized reason</failure></testcase>'
        "</testsuite>",
        encoding="utf-8",
    )

    assert sanitizer.scan_artifacts(tmp_path) == {}
    assert sanitizer.sanitize_artifacts(tmp_path) == {}


def test_artifact_scan_finds_credentials_in_files_and_zip_members(
    tmp_path: Path,
) -> None:
    (tmp_path / "session.txt").write_text(
        f"Cookie: portfolio_session=opaque-session-value\n"
        f"X-CSRF-Token: {'a' * 43}\n"
        "Authorization: Bearer opaquecredentialvalue123456\n"
        "eyJheaderabc.eyJpayloadabc.signatureabc",
        encoding="utf-8",
    )
    with zipfile.ZipFile(tmp_path / "trace.zip", "w") as archive:
        archive.writestr(
            "trace.network",
            "https://web.test/callback?code=private-code&state=opaque",
        )
        archive.writestr(
            "key.txt",
            "-----BEGIN PRIVATE KEY-----\nnot-public\n-----END PRIVATE KEY-----",
        )

    findings = sanitizer.scan_artifacts(tmp_path)

    assert findings[(tmp_path / "session.txt").as_posix()] == [
        "JWT material",
        "Web session cookie",
        "bearer authorization value",
        "CSRF token value",
    ]
    assert findings[f"{(tmp_path / 'trace.zip').as_posix()}!trace.network"] == [
        "OIDC authorization code"
    ]
    assert findings[f"{(tmp_path / 'trace.zip').as_posix()}!key.txt"] == ["private-key material"]

    sanitized = sanitizer.sanitize_artifacts(tmp_path)

    assert len(sanitized) == 3
    assert sanitizer.scan_artifacts(tmp_path) == {}
    sanitized_session = (tmp_path / "session.txt").read_text(encoding="utf-8")
    assert "opaque-session-value" not in sanitized_session
    assert "opaquecredentialvalue123456" not in sanitized_session
    with zipfile.ZipFile(tmp_path / "trace.zip") as archive:
        assert b"private-code" not in archive.read("trace.network")
        assert b"not-public" not in archive.read("key.txt")


def test_workflow_sanitizes_before_failure_upload_and_always_tears_down() -> None:
    workflow = (REPOSITORY_ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")

    scan = workflow.index("Scan verification artifacts for credential leakage")
    upload = workflow.index("Upload failure evidence")
    teardown = workflow.index("Tear down the isolated Compose project")
    assert scan < upload < teardown
    assert "if: failure() && steps.artifact_safety.outcome == 'success'" in workflow
    assert "if: always() && steps.plan.outputs.needs_runtime == 'true'" in workflow
