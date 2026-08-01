from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import tempfile
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_from_bytes


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_ROOT = REPOSITORY_ROOT / "artifacts" / "verification"
REPORT_NAME = "artifact-leak-scan.json"
CANARY_MANIFEST_NAME = ".artifact-sensitive-canaries.json"
CANARY_CATEGORIES = frozenset(
    {"private profile claim", "submitted private data", "submitted source text"}
)
PRIVATE_BROWSER_DIRECTORIES = frozenset({"playwright", "playwright-report"})
PRIVATE_BROWSER_SUFFIXES = frozenset({".jpeg", ".jpg", ".mp4", ".pdf", ".png", ".webm"})
Replacement = bytes | Callable[[re.Match[bytes]], bytes]


@dataclass(frozen=True, slots=True)
class SecretPattern:
    label: str
    expression: re.Pattern[bytes]
    replacement: Replacement


@dataclass(frozen=True, slots=True)
class SensitiveCanary:
    category: str
    value: bytes

    @property
    def replacement(self) -> bytes:
        slug = self.category.replace(" ", "-").encode("ascii")
        return b"[redacted-" + slug + b"]"


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


def load_sensitive_canaries(root: Path) -> tuple[SensitiveCanary, ...]:
    manifest = root / CANARY_MANIFEST_NAME
    if not manifest.is_file():
        return ()
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(
            "The artifact sensitive-canary manifest is invalid."
        ) from error
    if not isinstance(payload, dict) or set(payload) != {"version", "canaries"}:
        raise ValueError("The artifact sensitive-canary manifest shape is invalid.")
    if payload["version"] != 1 or not isinstance(payload["canaries"], list):
        raise ValueError("The artifact sensitive-canary manifest version is invalid.")

    canaries: list[SensitiveCanary] = []
    seen: set[tuple[str, bytes]] = set()
    for item in payload["canaries"]:
        if not isinstance(item, dict) or set(item) != {
            "category",
            "encoding",
            "value",
        }:
            raise ValueError("A sensitive-canary entry shape is invalid.")
        category = item["category"]
        encoding = item["encoding"]
        encoded_value = item["value"]
        if (
            category not in CANARY_CATEGORIES
            or encoding not in {"base64", "utf8"}
            or not isinstance(encoded_value, str)
        ):
            raise ValueError("A sensitive-canary entry is invalid.")
        try:
            value = (
                base64.b64decode(encoded_value, validate=True)
                if encoding == "base64"
                else encoded_value.encode("utf-8")
            )
        except (UnicodeEncodeError, binascii.Error) as error:
            raise ValueError("A sensitive-canary value is invalid.") from error
        if len(value) < 8:
            raise ValueError("Sensitive-canary values must contain at least 8 bytes.")
        identity = (category, value)
        if identity not in seen:
            seen.add(identity)
            canaries.append(SensitiveCanary(category=category, value=value))
    if not canaries:
        raise ValueError("The artifact sensitive-canary manifest is empty.")
    return tuple(canaries)


def canary_variants(value: bytes) -> tuple[bytes, ...]:
    variants = {
        value,
        base64.b64encode(value),
        base64.urlsafe_b64encode(value),
        base64.urlsafe_b64encode(value).rstrip(b"="),
        quote_from_bytes(value).encode("ascii"),
    }
    return tuple(
        sorted((item for item in variants if len(item) >= 8), key=len, reverse=True)
    )


def private_browser_container(root: Path, path: Path) -> bool:
    relative = path.relative_to(root)
    private_directory = bool(
        PRIVATE_BROWSER_DIRECTORIES.intersection(
            part.casefold() for part in relative.parts
        )
    )
    return (
        private_directory
        or (
            relative.parent == Path(".")
            and path.suffix.casefold() in PRIVATE_BROWSER_SUFFIXES
        )
        or path.name.casefold() == "trace.zip"
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


def sanitize_content(
    location: str,
    content: bytes,
    canaries: Iterable[SensitiveCanary] = (),
) -> tuple[bytes, list[str]]:
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
    for canary in canaries:
        found = False
        for variant in canary_variants(canary.value):
            if variant in content:
                found = True
                content = content.replace(variant, canary.replacement)
        if found:
            labels.append(canary.category)
    return content, list(dict.fromkeys(labels))


def sanitize_artifacts(
    root: Path,
    canaries: Iterable[SensitiveCanary] | None = None,
) -> dict[str, list[str]]:
    sanitized: dict[str, list[str]] = {}
    if not root.exists():
        return sanitized
    resolved_canaries = (
        load_sensitive_canaries(root) if canaries is None else tuple(canaries)
    )
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name in {CANARY_MANIFEST_NAME, REPORT_NAME}:
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
                        cleaned, labels = sanitize_content(
                            location, content, resolved_canaries
                        )
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
        cleaned, labels = sanitize_content(path.as_posix(), content, resolved_canaries)
        if labels:
            path.write_bytes(cleaned)
            sanitized[path.as_posix()] = labels
    return sanitized


def scan_artifacts(
    root: Path,
    canaries: Iterable[SensitiveCanary] | None = None,
) -> dict[str, list[str]]:
    findings: dict[str, list[str]] = {}
    if not root.exists():
        return findings
    resolved_canaries = (
        load_sensitive_canaries(root) if canaries is None else tuple(canaries)
    )
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name in {CANARY_MANIFEST_NAME, REPORT_NAME}:
            continue
        if private_browser_container(root, path):
            findings[path.as_posix()] = ["private browser artifact container"]
            continue
        for location, content in payloads(path):
            scannable = scannable_content(location, content)
            labels = [
                secret.label
                for secret in FORBIDDEN_PATTERNS
                if secret.expression.search(scannable)
            ]
            labels.extend(
                canary.category
                for canary in resolved_canaries
                if any(variant in content for variant in canary_variants(canary.value))
            )
            if labels:
                findings[location] = list(dict.fromkeys(labels))
    return findings


def write_report(
    root: Path,
    scanned_files: int,
    sanitized: dict[str, list[str]],
    canaries: Iterable[SensitiveCanary] = (),
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    resolved_canaries = tuple(canaries)
    labels = list(
        dict.fromkeys(
            [secret.label for secret in FORBIDDEN_PATTERNS] + sorted(CANARY_CATEGORIES)
        )
    )
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
                "registeredCanaryCategories": sorted(
                    {canary.category for canary in resolved_canaries}
                ),
                "privateBrowserArtifacts": "excluded from public artifact root",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Sanitize and reject credentials and registered private content in "
            "verification artifacts."
        )
    )
    parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.artifacts.resolve()
    canaries = load_sensitive_canaries(root)
    sanitized = sanitize_artifacts(root, canaries)
    (root / CANARY_MANIFEST_NAME).unlink(missing_ok=True)
    findings = scan_artifacts(root, canaries)
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
    write_report(root, scanned_files, sanitized, canaries)
    print(
        "Verification artifact leakage scan passed for "
        f"{scanned_files} files; sanitized {len(sanitized)} payloads."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
