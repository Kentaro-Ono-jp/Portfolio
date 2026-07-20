from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import unquote


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
IGNORED_PREFIXES = ("#", "http://", "https://", "mailto:")
REQUIRED_GOVERNANCE_FILES = (
    Path("docs/adr/0006-consolidate-ai-guidance.md"),
    Path("GIT_AGENTS.md"),
    Path("AI_GUIDANCE.md"),
    Path("docs/ai/README.md"),
    Path("docs/ai/PR_REVIEW.md"),
    Path(".github/workflows/CI_PLAYBOOK.md"),
)
EXPECTED_AI_GUIDANCE_FILES = frozenset(
    {
        Path("README.md"),
        Path("PR_REVIEW.md"),
    }
)
EXCLUDED_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "build",
        "coverage",
        "dist",
        "htmlcov",
        "node_modules",
    }
)
REQUIRED_GOVERNANCE_TEXT = {
    Path("GIT_AGENTS.md"): (
        "explicit, tracked entrypoint",
        "docs/ai/README.md",
        "docs/ai/PR_REVIEW.md",
        "Issue #1 and only the focused Issue",
        "Local memory and earlier conversations are orientation only",
        "python scripts/verify.py",
        ".github/workflows/CI_PLAYBOOK.md",
        "Never use global Docker cleanup",
        "Stop the pending mutation",
    ),
    Path("AI_GUIDANCE.md"): (
        "GIT_AGENTS.md",
        "not a second source of rules",
    ),
    Path("README.md"): (
        "AI-assisted engineering evidence",
        "GIT_AGENTS.md",
        "docs/ai/PR_REVIEW.md",
        "comment-only GitHub write authority",
    ),
    Path("docs/ai/README.md"): (
        "Authority order",
        "Does not independently mutate",
        "Do not enumerate every branch",
        "Explicit owner direction is required",
        "recoverable task checkpoint",
        ".github/workflows/CI_PLAYBOOK.md",
        "Completion evidence",
        "umbrella gate",
        "remote-branch deletion",
        "Do not infer current PR, Issue, check, or merge state from local memory",
        "Unsolicited public input",
    ),
    Path("docs/ai/PR_REVIEW.md"): (
        "Review cycle",
        "Previous verdict",
        "--depth 1",
        "--no-tags",
        "The only permitted GitHub write",
        "Do not push",
        "complete pull request diff",
        "Do not modify implementation",
        "short, uniquely named direct child",
        "extended-length path handling",
        "temporary path no longer exists",
        "cleanup scheduled immediately after this comment",
    ),
    Path("docs/adr/0006-consolidate-ai-guidance.md"): (
        "GIT_AGENTS.md",
        "two-file",
        "will not auto-discover",
        "one authoritative home",
    ),
    Path(".github/workflows/CI_PLAYBOOK.md"): (
        "Staged pre-commit hardening",
        "Local rehearsal boundaries",
        "External timeout termination is not verification evidence",
        "Post-merge knowledge reconciliation",
        "After every feature PR merge",
        "no new reusable finding",
        "Change-driven first-push checks",
        "Failed-run triage and promotion",
        "Historical evidence ledger",
        "total 11",
    ),
}
GOVERNANCE_ROOT_FILES = (
    Path("GIT_AGENTS.md"),
    Path("AI_GUIDANCE.md"),
    Path(".github/workflows/CI_PLAYBOOK.md"),
)
FORBIDDEN_GOVERNANCE_PATTERNS = {
    "Windows absolute path": re.compile(r"(?i)(?<![a-z0-9_])[a-z]:[\\/]"),
    "POSIX absolute path": re.compile(r"(?<![\w/:<.~])/(?!/)[^\s`'\"><\])}]+"),
    "UNC absolute path": re.compile(
        r"(?<![\\\w])\\\\[^\\/\s`'\"><]+[\\/][^\\/\s`'\"><]+"
    ),
    "local file URI": re.compile(r"(?i)\bfile:(?:/{1,3}|\\\\)"),
    "user-home shorthand path": re.compile(r"(?<![\w~])~[\\/]"),
    "machine-local memory path": re.compile(r"(?i)\.codex[\\/]memories"),
    "PEM private key": re.compile(r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----"),
    "GitHub credential": re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"
    ),
    "cloud access credential": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "Bearer credential": re.compile(
        r"(?i)\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._~+/=-]{16,}"
    ),
    "assigned credential": re.compile(
        r"(?im)\b(?:api[_ -]?(?:key|token)|access[_ -]?token|auth[_ -]?token|"
        r"client[_ -]?secret|password|passwd|token|secret)\b\s*[:=]\s*[\"']?"
        r"(?!(?:<[^>\r\n]+>|\$\{[^}\r\n]+\}|"
        r"(?:\[?redacted\]?|example|placeholder|changeme|none|null)\b))"
        r"[A-Za-z0-9._~+/=-]{8,}"
    ),
    "explicit private context": re.compile(
        r"(?im)^\s*(?:(?:private|confidential|client[ _-]?internal|"
        r"company[ _-]?internal)[ _-]*(?:context|note|data|source|details?)?|"
        r"(?:client|customer|employer)[ _-]+(?:name|context|data|source|details?))"
        r"\s*[:=]\s*(?!(?:<[^>\r\n]+>|\[?redacted\]?|example|placeholder|"
        r"none)\s*$)\S.+$"
    ),
}


def iter_markdown_files() -> list[Path]:
    markdown_files: list[Path] = []
    for directory, directory_names, file_names in os.walk(
        REPOSITORY_ROOT, topdown=True
    ):
        directory_names[:] = [
            name for name in directory_names if name not in EXCLUDED_DIRECTORY_NAMES
        ]
        directory_path = Path(directory)
        markdown_files.extend(
            directory_path / name for name in file_names if name.endswith(".md")
        )
    return sorted(markdown_files)


def local_target(raw_target: str) -> str | None:
    target = raw_target.strip().strip("<>").split(maxsplit=1)[0]
    if target.startswith(IGNORED_PREFIXES):
        return None
    return unquote(target.split("#", maxsplit=1)[0])


def governance_failures() -> list[str]:
    failures: list[str] = []

    for relative_path in REQUIRED_GOVERNANCE_FILES:
        if not (REPOSITORY_ROOT / relative_path).is_file():
            failures.append(
                f"missing required governance file {relative_path.as_posix()}"
            )

    for relative_path, required_fragments in REQUIRED_GOVERNANCE_TEXT.items():
        path = REPOSITORY_ROOT / relative_path
        if not path.is_file():
            failures.append(f"missing governance entrypoint {relative_path.as_posix()}")
            continue
        content = path.read_text(encoding="utf-8")
        normalized_content = " ".join(content.split())
        for fragment in required_fragments:
            if fragment not in normalized_content:
                failures.append(
                    f"{relative_path.as_posix()}: missing governance invariant {fragment!r}"
                )

    governance_paths = [
        REPOSITORY_ROOT / path
        for path in GOVERNANCE_ROOT_FILES
        if (REPOSITORY_ROOT / path).is_file()
    ]
    governance_root = REPOSITORY_ROOT / "docs" / "ai"
    if governance_root.is_dir():
        actual_ai_guidance_files = frozenset(
            path.relative_to(governance_root)
            for path in governance_root.rglob("*")
            if path.is_file()
        )
        for unexpected_path in sorted(
            actual_ai_guidance_files - EXPECTED_AI_GUIDANCE_FILES
        ):
            failures.append(
                f"docs/ai contains unexpected file {unexpected_path.as_posix()}"
            )
        for missing_path in sorted(
            EXPECTED_AI_GUIDANCE_FILES - actual_ai_guidance_files
        ):
            failures.append(
                f"docs/ai is missing required file {missing_path.as_posix()}"
            )
        governance_paths.extend(sorted(governance_root.rglob("*.md")))

    for path in governance_paths:
        content = path.read_text(encoding="utf-8")
        for label, pattern in FORBIDDEN_GOVERNANCE_PATTERNS.items():
            if pattern.search(content):
                relative_path = path.relative_to(REPOSITORY_ROOT)
                failures.append(
                    f"{relative_path.as_posix()}: contains forbidden {label}"
                )

    return failures


def main() -> int:
    failures = governance_failures()
    checked_links = 0

    for document in iter_markdown_files():
        content = document.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK.finditer(content):
            target = local_target(match.group(1))
            if not target:
                continue
            checked_links += 1
            resolved = (document.parent / target).resolve()
            if not resolved.exists():
                relative_document = document.relative_to(REPOSITORY_ROOT)
                failures.append(f"{relative_document}: missing link target {target}")

    if failures:
        print("Documentation link validation failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(
        f"Validated {checked_links} local links across "
        f"{len(iter_markdown_files())} Markdown files and the repository-owned "
        "AI governance invariants."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
