from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
IGNORED_PREFIXES = ("#", "http://", "https://", "mailto:")
REQUIRED_GOVERNANCE_FILES = (
    Path("docs/adr/0005-repository-owned-ai-collaboration.md"),
    Path("docs/ai/README.md"),
    Path("docs/ai/operating-contract.md"),
    Path("docs/ai/task-lifecycle.md"),
    Path("docs/ai/evidence-policy.md"),
    Path("docs/ai/prompts/README.md"),
    Path("docs/ai/prompts/task-bootstrap.md"),
    Path("docs/ai/prompts/independent-review.md"),
    Path("docs/ai/prompts/post-merge-reconciliation.md"),
)
REQUIRED_GOVERNANCE_TEXT = {
    Path("AGENTS.md"): (
        "docs/ai/README.md",
        "live project ledger",
        "Exact checks remain mandatory",
    ),
    Path("CLAUDE.md"): (
        "docs/ai/README.md",
        "non-authoritative orientation only",
    ),
    Path("README.md"): (
        "AI-assisted engineering evidence",
        "comment-only GitHub write authority",
    ),
    Path("docs/ai/README.md"): (
        "Source-of-truth order",
        "Live state is not duplicated here",
        "non-authoritative orientation only",
    ),
    Path("docs/ai/operating-contract.md"): (
        "isolated temporary shallow clone",
        "exactly one GitHub write",
        "must not push",
        "Unsolicited comments",
        "does not independently perform Git or GitHub mutations",
    ),
    Path("docs/ai/task-lifecycle.md"): (
        "Do not list all Issues, branches, comments",
        "verify the exact target",
        "does not audit every remote and local object",
        "recoverable task checkpoint",
    ),
    Path("docs/ai/evidence-policy.md"): (
        "Completion evidence",
        "Umbrella Issue #1",
        "does not edit Issue checklists",
    ),
    Path("docs/ai/prompts/independent-review.md"): (
        "--depth 1",
        "--no-tags",
        "only permitted GitHub write",
        "Do not push",
        "temporary path no longer exists",
    ),
}
FORBIDDEN_GOVERNANCE_PATTERNS = {
    "Windows absolute path": re.compile(r"(?i)(?<![a-z0-9_])[a-z]:[\\/]"),
    "POSIX absolute path": re.compile(r"(?<![\w/:<.~])/(?!/)[^\s`'\"><\])}]+"),
    "UNC absolute path": re.compile(
        r"(?<![\\\w])\\\\[^\\/\s`'\"><]+[\\/][^\\/\s`'\"><]+"
    ),
    "local file URI": re.compile(r"(?i)\bfile:(?:/{1,3}|\\\\)"),
    "user-home shorthand path": re.compile(r"(?<![\w~])~[\\/]"),
    "machine-local memory path": re.compile(r"(?i)\.codex[\\/]memories"),
}


def iter_markdown_files() -> list[Path]:
    excluded = {
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
    return sorted(
        path
        for path in REPOSITORY_ROOT.rglob("*.md")
        if not excluded.intersection(path.relative_to(REPOSITORY_ROOT).parts)
    )


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

    governance_root = REPOSITORY_ROOT / "docs" / "ai"
    if governance_root.is_dir():
        for path in sorted(governance_root.rglob("*.md")):
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
