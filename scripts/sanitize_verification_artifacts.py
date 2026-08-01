from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_ROOT = REPOSITORY_ROOT / "artifacts" / "verification"
REPORT_NAME = "artifact-leak-scan.json"
Replacement = bytes | Callable[[re.Match[bytes]], bytes]


@dataclass(frozen=True, slots=True)
class SecretPattern:
    label: str
    expression: re.Pattern[bytes]
    replacement: Replacement


def redact_after_prefix(match: re.Match[bytes]) -> bytes:
    return match.group("prefix") + b"[redacted]"


FORBIDDEN_PATTERNS: tuple[SecretPattern, ...] = (
    SecretPattern(
        "private-key material",
        re.compile(
            rb"-----BEGIN (?P<kind>(?:RSA |EC |OPENSSH )?PRIVATE KEY)-----.*?"
            rb"(?:-----END (?P=kind)-----|$)",
            re.DOTALL,
        ),
        b"[redacted-private-key]",
    ),
    SecretPattern(
        "JWT material",
        re.compile(rb"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
        b"[redacted-jwt]",
    ),
    SecretPattern(
        "Web session cookie",
        re.compile(
            rb"(?P<prefix>portfolio_session(?:=|%3D))[A-Za-z0-9._~+/%-]+",
            re.IGNORECASE,
        ),
        redact_after_prefix,
    ),
    SecretPattern(
        "OIDC authorization code",
        re.compile(
            rb"(?P<prefix>(?:[?&]|%3F|%26)code(?:=|%3D))"
            rb"[A-Za-z0-9._~+/%-]+",
            re.IGNORECASE,
        ),
        redact_after_prefix,
    ),
    SecretPattern(
        "bearer authorization value",
        re.compile(
            rb"(?P<prefix>authorization(?:\"|')?\s*[:=]\s*"
            rb"(?:\"|')?bearer\s+)[A-Za-z0-9._~+/%-]{16,}",
            re.IGNORECASE,
        ),
        redact_after_prefix,
    ),
    SecretPattern(
        "CSRF token value",
        re.compile(
            rb"(?P<prefix>x-csrf-token(?:\"|')?\s*[:=]\s*"
            rb"(?:\"|')?)[A-Za-z0-9_-]{40,}",
            re.IGNORECASE,
        ),
        redact_after_prefix,
    ),
    SecretPattern(
        "CSRF token value",
        re.compile(
            rb"(?P<prefix>[\"']name[\"']\s*:\s*[\"']x-csrf-token[\"']\s*,"
            rb"\s*[\"']value[\"']\s*:\s*[\"'])[A-Za-z0-9_-]{40,}",
            re.IGNORECASE,
        ),
        redact_after_prefix,
    ),
)


def payloads(path: Path) -> Iterable[tuple[str, bytes]]:
    location = path.as_posix()
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                yield f"{location}!{member.filename}", archive.read(member)
        return
    yield location, path.read_bytes()


def scannable_content(location: str, content: bytes) -> bytes:
    if location.lower().endswith(".xml"):
        # Parameterized security tests intentionally place forbidden examples in
        # JUnit testcase names. Runtime output and failure bodies remain scanned.
        return re.sub(rb"<testcase\b[^>]*>", b"<testcase>", content)
    return content


def sanitize_content(location: str, content: bytes) -> tuple[bytes, list[str]]:
    protected_tags: list[bytes] = []

    def protect_testcase(match: re.Match[bytes]) -> bytes:
        index = len(protected_tags)
        protected_tags.append(match.group(0))
        return f"__REACTORFRONT_TESTCASE_{index:08d}__".encode()

    if location.lower().endswith(".xml"):
        content = re.sub(rb"<testcase\b[^>]*>", protect_testcase, content)
    labels: list[str] = []
    for secret in FORBIDDEN_PATTERNS:
        if secret.expression.search(content):
            labels.append(secret.label)
            content = secret.expression.sub(secret.replacement, content)
    for index, tag in enumerate(protected_tags):
        placeholder = f"__REACTORFRONT_TESTCASE_{index:08d}__".encode()
        content = content.replace(placeholder, tag)
    return content, list(dict.fromkeys(labels))


def sanitize_artifacts(root: Path) -> dict[str, list[str]]:
    sanitized: dict[str, list[str]] = {}
    if not root.exists():
        return sanitized
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == REPORT_NAME:
            continue
        if zipfile.is_zipfile(path):
            changed = False
            member_labels: dict[str, list[str]] = {}
            with tempfile.NamedTemporaryFile(
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
            try:
                with (
                    zipfile.ZipFile(path) as source,
                    zipfile.ZipFile(temporary_path, "w") as target,
                ):
                    for member in source.infolist():
                        content = source.read(member) if not member.is_dir() else b""
                        location = f"{path.as_posix()}!{member.filename}"
                        cleaned, labels = sanitize_content(location, content)
                        if labels:
                            changed = True
                            member_labels[location] = labels
                        target.writestr(member, cleaned)
                if changed:
                    os.replace(temporary_path, path)
                    sanitized.update(member_labels)
                else:
                    temporary_path.unlink()
            except Exception:
                temporary_path.unlink(missing_ok=True)
                raise
            continue
        content = path.read_bytes()
        cleaned, labels = sanitize_content(path.as_posix(), content)
        if labels:
            path.write_bytes(cleaned)
            sanitized[path.as_posix()] = labels
    return sanitized


def scan_artifacts(root: Path) -> dict[str, list[str]]:
    findings: dict[str, list[str]] = {}
    if not root.exists():
        return findings
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == REPORT_NAME:
            continue
        for location, content in payloads(path):
            content = scannable_content(location, content)
            labels = [
                secret.label
                for secret in FORBIDDEN_PATTERNS
                if secret.expression.search(content)
            ]
            if labels:
                findings[location] = list(dict.fromkeys(labels))
    return findings


def write_report(
    root: Path, scanned_files: int, sanitized: dict[str, list[str]]
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    labels = list(dict.fromkeys(secret.label for secret in FORBIDDEN_PATTERNS))
    (root / REPORT_NAME).write_text(
        json.dumps(
            {
                "status": "passed",
                "scannedFiles": scanned_files,
                "sanitizedPayloads": len(sanitized),
                "sanitizedPatternCounts": {
                    label: sum(label in found for found in sanitized.values())
                    for label in labels
                },
                "forbiddenPatterns": labels,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sanitize and reject credential material in verification artifacts."
    )
    parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.artifacts.resolve()
    sanitized = sanitize_artifacts(root)
    findings = scan_artifacts(root)
    if findings:
        print("Verification artifact leakage scan failed:")
        for location, found in sorted(findings.items()):
            safe_location = Path(location.split("!", 1)[0]).name
            print(f"- {safe_location}: {', '.join(found)}")
        return 1
    scanned_files = (
        sum(
            1 for path in root.rglob("*") if path.is_file() and path.name != REPORT_NAME
        )
        if root.exists()
        else 0
    )
    write_report(root, scanned_files, sanitized)
    print(
        "Verification artifact leakage scan passed for "
        f"{scanned_files} files; sanitized {len(sanitized)} payloads."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
