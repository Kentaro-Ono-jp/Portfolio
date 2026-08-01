from __future__ import annotations

import base64
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote_from_bytes

import pytest
from scripts import sanitize_verification_artifacts as sanitizer

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def independently_encoded_variants(value: bytes) -> tuple[bytes, ...]:
    strict_percent = quote_from_bytes(value, safe="").encode("ascii")
    lowercase_percent = bytearray()
    index = 0
    while index < len(strict_percent):
        if strict_percent[index : index + 1] == b"%":
            lowercase_percent.extend(b"%")
            lowercase_percent.extend(strict_percent[index + 1 : index + 3].lower())
            index += 3
        else:
            lowercase_percent.append(strict_percent[index])
            index += 1
    return (
        value,
        base64.b64encode(value),
        base64.urlsafe_b64encode(value),
        base64.urlsafe_b64encode(value).rstrip(b"="),
        strict_percent,
        bytes(lowercase_percent),
    )


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
    with zipfile.ZipFile(tmp_path / "diagnostics.zip", "w") as archive:
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
    assert findings[f"{(tmp_path / 'diagnostics.zip').as_posix()}!trace.network"] == [
        "OIDC authorization code"
    ]
    assert findings[f"{(tmp_path / 'diagnostics.zip').as_posix()}!key.txt"] == [
        "private-key material"
    ]

    sanitized = sanitizer.sanitize_artifacts(tmp_path)

    assert len(sanitized) == 3
    assert sanitizer.scan_artifacts(tmp_path) == {}
    sanitized_session = (tmp_path / "session.txt").read_text(encoding="utf-8")
    assert "opaque-session-value" not in sanitized_session
    assert "opaquecredentialvalue123456" not in sanitized_session
    with zipfile.ZipFile(tmp_path / "diagnostics.zip") as archive:
        assert b"private-code" not in archive.read("trace.network")
        assert b"not-public" not in archive.read("key.txt")


def test_artifact_scan_uses_registered_private_content_canaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_text = "opaque submitted source sentence"
    profile_claim = "opaque-profile-claim-value"
    submitted_data = b"opaque submitted private binary data"
    (tmp_path / sanitizer.CANARY_MANIFEST_NAME).write_text(
        json.dumps(
            {
                "version": 1,
                "canaries": [
                    {
                        "category": "submitted source text",
                        "encoding": "utf8",
                        "value": source_text,
                    },
                    {
                        "category": "private profile claim",
                        "encoding": "utf8",
                        "value": profile_claim,
                    },
                    {
                        "category": "submitted private data",
                        "encoding": "base64",
                        "value": base64.b64encode(submitted_data).decode("ascii"),
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "ordinary.json").write_text(
        json.dumps({"source": source_text, "profile": profile_claim}),
        encoding="utf-8",
    )
    with zipfile.ZipFile(tmp_path / "diagnostics.zip", "w") as archive:
        archive.writestr("resource.body", base64.b64encode(submitted_data))

    canaries = sanitizer.load_sensitive_canaries(tmp_path)
    findings = sanitizer.scan_artifacts(tmp_path, canaries)

    assert findings[(tmp_path / "ordinary.json").as_posix()] == [
        "submitted source text",
        "private profile claim",
    ]
    assert findings[f"{(tmp_path / 'diagnostics.zip').as_posix()}!resource.body"] == [
        "submitted private data"
    ]

    monkeypatch.setattr(
        sanitizer,
        "parse_args",
        lambda: SimpleNamespace(artifacts=tmp_path),
    )
    assert sanitizer.main() == 0

    assert not (tmp_path / sanitizer.CANARY_MANIFEST_NAME).exists()
    assert sanitizer.scan_artifacts(tmp_path, canaries) == {}
    assert source_text not in (tmp_path / "ordinary.json").read_text(encoding="utf-8")
    assert profile_claim not in (tmp_path / "ordinary.json").read_text(encoding="utf-8")
    with zipfile.ZipFile(tmp_path / "diagnostics.zip") as archive:
        assert base64.b64encode(submitted_data) not in archive.read("resource.body")
    report_text = (tmp_path / sanitizer.REPORT_NAME).read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert source_text not in report_text
    assert profile_claim not in report_text
    assert base64.b64encode(submitted_data).decode("ascii") not in report_text
    assert report["sanitizedPayloads"] == 2
    assert report["registeredCanaryCategories"] == sorted(sanitizer.CANARY_CATEGORIES)


def test_artifact_scan_covers_independently_encoded_canary_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submitted_pdf = b"%PDF-1.7\n/Type /Catalog /Pages private-body\xfb\xff"
    variants = independently_encoded_variants(submitted_pdf)
    assert quote_from_bytes(submitted_pdf, safe="").encode("ascii") in variants
    assert b"%2FType" in variants[-2]
    assert b"%2fType" in variants[-1]
    (tmp_path / sanitizer.CANARY_MANIFEST_NAME).write_text(
        json.dumps(
            {
                "version": 1,
                "canaries": [
                    {
                        "category": "submitted private data",
                        "encoding": "base64",
                        "value": base64.b64encode(submitted_pdf).decode("ascii"),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    separator = b"\n--independent-variant--\n"
    (tmp_path / "ordinary.bin").write_bytes(separator.join(variants))
    with zipfile.ZipFile(tmp_path / "diagnostics.zip", "w") as archive:
        archive.writestr("resource.body", separator.join(reversed(variants)))

    canaries = sanitizer.load_sensitive_canaries(tmp_path)
    findings = sanitizer.scan_artifacts(tmp_path, canaries)
    assert findings[(tmp_path / "ordinary.bin").as_posix()] == ["submitted private data"]
    assert findings[f"{(tmp_path / 'diagnostics.zip').as_posix()}!resource.body"] == [
        "submitted private data"
    ]

    monkeypatch.setattr(
        sanitizer,
        "parse_args",
        lambda: SimpleNamespace(artifacts=tmp_path),
    )
    assert sanitizer.main() == 0
    assert sanitizer.scan_artifacts(tmp_path, canaries) == {}
    ordinary = (tmp_path / "ordinary.bin").read_bytes()
    with zipfile.ZipFile(tmp_path / "diagnostics.zip") as archive:
        zipped = archive.read("resource.body")
    for variant in variants:
        assert variant not in ordinary
        assert variant not in zipped


def test_unexpected_runtime_profile_canary_is_redacted_from_junit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_actor = "11111111-1111-4111-8111-111111111111"
    unexpected_actor = "22222222-2222-4222-8222-222222222222"
    (tmp_path / sanitizer.CANARY_MANIFEST_NAME).write_text(
        json.dumps(
            {
                "version": 1,
                "canaries": [
                    {
                        "category": "private profile claim",
                        "encoding": "utf8",
                        "value": expected_actor,
                    },
                    {
                        "category": "private profile claim",
                        "encoding": "utf8",
                        "value": unexpected_actor,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    junit = tmp_path / "playwright-junit.xml"
    junit.write_text(
        f"<failure>expected {expected_actor}, received {unexpected_actor}</failure>",
        encoding="utf-8",
    )

    canaries = sanitizer.load_sensitive_canaries(tmp_path)
    assert sanitizer.scan_artifacts(tmp_path, canaries) == {
        junit.as_posix(): ["private profile claim"]
    }
    monkeypatch.setattr(
        sanitizer,
        "parse_args",
        lambda: SimpleNamespace(artifacts=tmp_path),
    )
    assert sanitizer.main() == 0
    sanitized_junit = junit.read_text(encoding="utf-8")
    assert expected_actor not in sanitized_junit
    assert unexpected_actor not in sanitized_junit
    assert sanitizer.scan_artifacts(tmp_path, canaries) == {}


def test_public_artifact_root_rejects_private_browser_containers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playwright = tmp_path / "playwright"
    playwright.mkdir()
    with zipfile.ZipFile(playwright / "trace.zip", "w") as archive:
        archive.writestr("resources/source.pdf", b"opaque submitted data")
    (tmp_path / "failure.png").write_bytes(b"opaque rendered source")

    assert sanitizer.scan_artifacts(tmp_path) == {
        (tmp_path / "failure.png").as_posix(): ["private browser artifact container"],
        (playwright / "trace.zip").as_posix(): ["private browser artifact container"],
    }
    monkeypatch.setattr(
        sanitizer,
        "parse_args",
        lambda: SimpleNamespace(artifacts=tmp_path),
    )
    assert sanitizer.main() == 1


def test_workflow_sanitizes_before_failure_upload_and_always_tears_down() -> None:
    workflow = (REPOSITORY_ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")
    playwright_config = (REPOSITORY_ROOT / "playwright.config.ts").read_text(encoding="utf-8")
    browser_proof = (REPOSITORY_ROOT / "tests/e2e/document-classification.spec.ts").read_text(
        encoding="utf-8"
    )

    scan = workflow.index("Scan verification artifacts for private-content leakage")
    upload = workflow.index("Upload failure evidence")
    teardown = workflow.index("Tear down the isolated Compose project")
    assert scan < upload < teardown
    assert "if: failure() && steps.artifact_safety.outcome == 'success'" in workflow
    assert "if: always() && steps.plan.outputs.needs_runtime == 'true'" in workflow
    assert "artifacts/private-verification" not in workflow
    assert 'path.resolve("artifacts/private-verification")' in playwright_config
    assert "outputDir: path.join(privateArtifactRoot" in playwright_config
    assert "outputFolder: path.join(privateArtifactRoot" in playwright_config
    assert "outputFile: path.join(publicArtifactRoot" in playwright_config
    assert "writeSensitiveCanaryManifest(sensitiveCanaries)" in browser_proof
    register_profile = browser_proof.index("function registerObservedPrivateProfileCanaries(")
    register_audit_profiles = browser_proof.index("...events.map((event) =>", register_profile)
    validate_audit_events = browser_proof.index("return events.map((event) => {")
    register_approved_profile = browser_proof.index(
        "approved.reviewerPrincipalId,", validate_audit_events
    )
    validate_approved = browser_proof.index("expect(approved).toMatchObject({")
    register_corrected_profile = browser_proof.index(
        "corrected.reviewerPrincipalId,", validate_approved
    )
    validate_corrected = browser_proof.index("expect(corrected).toMatchObject({")
    assert register_audit_profiles < validate_audit_events
    assert register_approved_profile < validate_approved
    assert register_corrected_profile < validate_corrected
    assert 'path.join(PRIVATE_ARTIFACT_ROOT, "e2e-approved-review.png")' in browser_proof
    assert 'path.join(PRIVATE_ARTIFACT_ROOT, "e2e-corrected-review.png")' in browser_proof
