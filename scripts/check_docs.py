from __future__ import annotations

import os
import re
from collections import Counter, deque
from pathlib import Path
from urllib.parse import unquote


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
IGNORED_PREFIXES = ("#", "http://", "https://", "mailto:")

DOCFORAI_FILE_ROLES = {
    Path("docs/ai/README.md"): "router",
    Path("docs/ai/PR_REVIEW.md"): "router",
    Path("docs/ai/knowledge/README.md"): "router",
    Path("docs/ai/reference/authority.md"): "reference",
    Path("docs/ai/reference/live-state.md"): "reference",
    Path("docs/ai/reference/public-safety.md"): "reference",
    Path("docs/ai/reference/evidence.md"): "reference",
    Path("docs/ai/reference/local-tools.md"): "reference",
    Path("docs/ai/workflows/focus.md"): "procedure",
    Path("docs/ai/workflows/implement.md"): "procedure",
    Path("docs/ai/workflows/publish.md"): "procedure",
    Path("docs/ai/workflows/correct.md"): "procedure",
    Path("docs/ai/workflows/merge.md"): "procedure",
    Path("docs/ai/workflows/reconcile.md"): "procedure",
    Path("docs/ai/workflows/governance-reconcile.md"): "procedure",
    Path("docs/ai/review/setup.md"): "procedure",
    Path("docs/ai/review/inspect.md"): "procedure",
    Path("docs/ai/review/verdict.md"): "procedure",
    Path("docs/ai/review/cleanup.md"): "procedure",
    Path("docs/ai/ci/preflight.md"): "procedure",
    Path("docs/ai/ci/local-rehearsal.md"): "procedure",
    Path("docs/ai/ci/markdown-only.md"): "procedure",
    Path("docs/ai/ci/failure-triage.md"): "procedure",
    Path("docs/ai/ci/post-merge.md"): "procedure",
    Path("docs/ai/ci/knowledge/README.md"): "router",
    Path("docs/ai/ci/knowledge/dependencies.md"): "knowledge",
    Path("docs/ai/ci/knowledge/invocation.md"): "knowledge",
    Path("docs/ai/ci/knowledge/persistence.md"): "knowledge",
    Path("docs/ai/ci/knowledge/isolation.md"): "knowledge",
    Path("docs/ai/ci/knowledge/messaging.md"): "knowledge",
    Path("docs/ai/ci/knowledge/browser.md"): "knowledge",
    Path("docs/ai/ci/knowledge/recovery.md"): "knowledge",
    Path("docs/ai/ci/knowledge/evidence.md"): "knowledge",
}
ENTRYPOINT_FILE_ROLES = {
    Path("GIT_AGENTS.md"): "router",
    Path("AI_GUIDANCE.md"): "pointer",
    Path(".github/workflows/CI_PLAYBOOK.md"): "router",
}
EXPECTED_AI_GUIDANCE_FILES = frozenset(
    path.relative_to("docs/ai") for path in DOCFORAI_FILE_ROLES
)
REQUIRED_GOVERNANCE_FILES = (
    Path("docs/adr/0008-progressive-disclosure-ai-guidance.md"),
    Path("docs/adr/0009-reviewed-governance-knowledge-reconciliation.md"),
    Path("docs/delivery/README.md"),
    *ENTRYPOINT_FILE_ROLES,
    *DOCFORAI_FILE_ROLES,
)

ROUTER_LINE_BUDGETS = {
    Path("GIT_AGENTS.md"): 70,
    Path("AI_GUIDANCE.md"): 10,
    Path("docs/ai/README.md"): 100,
    Path("docs/ai/PR_REVIEW.md"): 65,
    Path("docs/ai/knowledge/README.md"): 75,
    Path(".github/workflows/CI_PLAYBOOK.md"): 45,
    Path("docs/ai/ci/knowledge/README.md"): 55,
}

CANONICAL_RULE_OWNERS = {
    "progressive-disclosure": Path("docs/ai/README.md"),
    "review-permission-boundary": Path("docs/ai/PR_REVIEW.md"),
    "governance-knowledge-selection": Path("docs/ai/knowledge/README.md"),
    "actor-authority": Path("docs/ai/reference/authority.md"),
    "bounded-live-state": Path("docs/ai/reference/live-state.md"),
    "public-safety": Path("docs/ai/reference/public-safety.md"),
    "issue-evidence": Path("docs/ai/reference/evidence.md"),
    "local-tool-authorization": Path("docs/ai/reference/local-tools.md"),
    "focus-workflow": Path("docs/ai/workflows/focus.md"),
    "implementation-workflow": Path("docs/ai/workflows/implement.md"),
    "publication-workflow": Path("docs/ai/workflows/publish.md"),
    "correction-workflow": Path("docs/ai/workflows/correct.md"),
    "merge-workflow": Path("docs/ai/workflows/merge.md"),
    "reconciliation-workflow": Path("docs/ai/workflows/reconcile.md"),
    "governance-knowledge-reconciliation": Path(
        "docs/ai/workflows/governance-reconcile.md"
    ),
    "review-setup": Path("docs/ai/review/setup.md"),
    "review-inspection": Path("docs/ai/review/inspect.md"),
    "review-verdict": Path("docs/ai/review/verdict.md"),
    "review-cleanup": Path("docs/ai/review/cleanup.md"),
    "ci-routing": Path(".github/workflows/CI_PLAYBOOK.md"),
    "ci-preflight": Path("docs/ai/ci/preflight.md"),
    "ci-local-rehearsal": Path("docs/ai/ci/local-rehearsal.md"),
    "ci-markdown-only-exception": Path("docs/ai/ci/markdown-only.md"),
    "ci-failure-triage": Path("docs/ai/ci/failure-triage.md"),
    "ci-post-merge": Path("docs/ai/ci/post-merge.md"),
    "ci-knowledge-selection": Path("docs/ai/ci/knowledge/README.md"),
    "ci-knowledge-dependencies": Path("docs/ai/ci/knowledge/dependencies.md"),
    "ci-knowledge-invocation": Path("docs/ai/ci/knowledge/invocation.md"),
    "ci-knowledge-persistence": Path("docs/ai/ci/knowledge/persistence.md"),
    "ci-knowledge-isolation": Path("docs/ai/ci/knowledge/isolation.md"),
    "ci-knowledge-messaging": Path("docs/ai/ci/knowledge/messaging.md"),
    "ci-knowledge-browser": Path("docs/ai/ci/knowledge/browser.md"),
    "ci-knowledge-recovery": Path("docs/ai/ci/knowledge/recovery.md"),
    "ci-knowledge-evidence": Path("docs/ai/ci/knowledge/evidence.md"),
}

REQUIRED_ROUTE_LINKS = {
    Path("GIT_AGENTS.md"): (
        Path("AI_GUIDANCE.md"),
        Path("docs/ai/README.md"),
        Path(".github/workflows/CI_PLAYBOOK.md"),
    ),
    Path("AI_GUIDANCE.md"): (Path("GIT_AGENTS.md"),),
    Path("docs/ai/README.md"): (
        Path("docs/ai/PR_REVIEW.md"),
        Path("docs/ai/reference/authority.md"),
        Path("docs/ai/reference/live-state.md"),
        Path("docs/ai/reference/local-tools.md"),
        Path("docs/ai/workflows/focus.md"),
        Path("docs/ai/workflows/implement.md"),
        Path("docs/ai/workflows/publish.md"),
        Path("docs/ai/workflows/correct.md"),
        Path("docs/ai/workflows/merge.md"),
        Path("docs/ai/workflows/reconcile.md"),
        Path("docs/ai/workflows/governance-reconcile.md"),
        Path(".github/workflows/CI_PLAYBOOK.md"),
        Path("docs/delivery/README.md"),
        Path("docs/adr/README.md"),
    ),
    Path("docs/ai/PR_REVIEW.md"): (Path("docs/ai/review/setup.md"),),
    Path("docs/ai/workflows/focus.md"): (
        Path("docs/delivery/README.md"),
        Path("docs/adr/README.md"),
        Path("docs/ai/reference/live-state.md"),
        Path("docs/ai/reference/public-safety.md"),
        Path("docs/ai/workflows/implement.md"),
    ),
    Path("docs/ai/workflows/implement.md"): (
        Path("docs/ai/workflows/focus.md"),
        Path("docs/ai/reference/local-tools.md"),
        Path("docs/ai/reference/public-safety.md"),
        Path(".github/workflows/CI_PLAYBOOK.md"),
        Path("docs/ai/workflows/publish.md"),
    ),
    Path("docs/ai/workflows/publish.md"): (
        Path("docs/ai/reference/live-state.md"),
        Path("docs/ai/ci/markdown-only.md"),
        Path("docs/ai/PR_REVIEW.md"),
        Path("docs/ai/workflows/focus.md"),
        Path("docs/ai/workflows/correct.md"),
        Path("docs/ai/workflows/merge.md"),
    ),
    Path("docs/ai/workflows/correct.md"): (
        Path("docs/ai/workflows/focus.md"),
        Path("docs/ai/workflows/implement.md"),
        Path("docs/ai/workflows/publish.md"),
        Path("docs/ai/workflows/merge.md"),
    ),
    Path("docs/ai/workflows/merge.md"): (
        Path("docs/ai/reference/live-state.md"),
        Path("docs/ai/ci/markdown-only.md"),
        Path(".github/workflows/CI_PLAYBOOK.md"),
        Path("docs/ai/workflows/reconcile.md"),
    ),
    Path("docs/ai/workflows/reconcile.md"): (
        Path(".github/workflows/CI_PLAYBOOK.md"),
        Path("docs/ai/workflows/governance-reconcile.md"),
        Path("docs/ai/reference/evidence.md"),
        Path("docs/ai/README.md"),
    ),
    Path("docs/ai/workflows/governance-reconcile.md"): (
        Path(".github/workflows/CI_PLAYBOOK.md"),
        Path("docs/ai/workflows/focus.md"),
        Path("docs/ai/knowledge/README.md"),
    ),
    Path("docs/ai/knowledge/README.md"): (
        Path("docs/ai/reference/authority.md"),
        Path("docs/ai/reference/live-state.md"),
        Path("docs/ai/reference/local-tools.md"),
        Path("docs/ai/reference/public-safety.md"),
        Path("docs/ai/reference/evidence.md"),
        Path("docs/ai/workflows/focus.md"),
        Path("docs/ai/workflows/implement.md"),
        Path("docs/ai/workflows/publish.md"),
        Path("docs/ai/workflows/correct.md"),
        Path("docs/ai/workflows/merge.md"),
        Path("docs/ai/workflows/reconcile.md"),
        Path("docs/ai/review/setup.md"),
        Path("docs/ai/review/inspect.md"),
        Path("docs/ai/review/verdict.md"),
        Path("docs/ai/review/cleanup.md"),
        Path(".github/workflows/CI_PLAYBOOK.md"),
        Path("docs/adr/README.md"),
        Path("docs/delivery/README.md"),
    ),
    Path("docs/ai/review/setup.md"): (
        Path("docs/ai/reference/local-tools.md"),
        Path("docs/ai/review/inspect.md"),
    ),
    Path("docs/ai/review/inspect.md"): (
        Path("docs/ai/reference/public-safety.md"),
        Path("docs/ai/ci/markdown-only.md"),
        Path("docs/ai/review/verdict.md"),
    ),
    Path("docs/ai/review/verdict.md"): (Path("docs/ai/review/cleanup.md"),),
    Path(".github/workflows/CI_PLAYBOOK.md"): (
        Path("docs/ai/ci/preflight.md"),
        Path("docs/ai/ci/local-rehearsal.md"),
        Path("docs/ai/ci/markdown-only.md"),
        Path("docs/ai/ci/failure-triage.md"),
        Path("docs/ai/ci/post-merge.md"),
        Path("docs/ai/ci/knowledge/README.md"),
        Path("docs/ai/README.md"),
    ),
    Path("docs/ai/ci/preflight.md"): (
        Path("docs/ai/ci/knowledge/README.md"),
        Path("docs/ai/ci/local-rehearsal.md"),
        Path("docs/ai/ci/failure-triage.md"),
    ),
    Path("docs/ai/ci/local-rehearsal.md"): (Path("docs/ai/reference/local-tools.md"),),
    Path("docs/ai/ci/failure-triage.md"): (
        Path("docs/ai/ci/knowledge/README.md"),
        Path("docs/ai/workflows/focus.md"),
    ),
    Path("docs/ai/ci/post-merge.md"): (Path("docs/ai/ci/knowledge/README.md"),),
    Path("docs/ai/ci/knowledge/README.md"): (
        Path("docs/ai/ci/knowledge/dependencies.md"),
        Path("docs/ai/ci/knowledge/invocation.md"),
        Path("docs/ai/ci/knowledge/persistence.md"),
        Path("docs/ai/ci/knowledge/isolation.md"),
        Path("docs/ai/ci/knowledge/messaging.md"),
        Path("docs/ai/ci/knowledge/browser.md"),
        Path("docs/ai/ci/knowledge/recovery.md"),
        Path("docs/ai/ci/knowledge/evidence.md"),
    ),
}

REQUIRED_GOVERNANCE_TEXT = {
    Path("GIT_AGENTS.md"): (
        "thin, tracked entrypoint",
        "open only that route",
        "python scripts/verify.py",
        "Never use global Docker cleanup",
        "Request a decision only when recovery requires selecting",
    ),
    Path("AI_GUIDANCE.md"): (
        "GIT_AGENTS.md",
        "not a second source of rules",
    ),
    Path("docs/ai/README.md"): (
        "progressive disclosure",
        "Select the first matching state",
        "Do not read all ADRs or delivery specifications",
        "A loop-back is valid only after state changed",
        "The only owner-confirmation STOP",
        "reusable non-CI process or review knowledge",
    ),
    Path("docs/ai/PR_REVIEW.md"): (
        "Governing tracking Issue URL",
        "Expected full head SHA",
        "The only permitted GitHub write",
        "Do not push",
        "open only the named next state",
    ),
    Path("docs/ai/reference/authority.md"): (
        "The only owner-confirmation boundary",
        "standing policy",
        "Docker-backed proof runs in GitHub Actions",
        "A Markdown-only skip is machine-qualified",
        "Only proved checklist criteria change state",
        "A remote branch is deleted only after",
        "Public participant",
    ),
    Path("docs/ai/reference/live-state.md"): (
        "Do not enumerate every branch",
        "Do not infer current PR, Issue, check, or merge state",
        "Deterministic recovery",
    ),
    Path("docs/ai/reference/evidence.md"): (
        "Completion evidence",
        "umbrella gate",
        "Check only fully proved criteria",
        "independent reviewer never edits Issue checklists",
    ),
    Path("docs/ai/reference/local-tools.md"): (
        "Do not request elevated privileges",
        "route Docker-backed or environment-dependent proof to GitHub Actions",
    ),
    Path("docs/ai/workflows/publish.md"): (
        "machine-qualified Markdown-only CI exception",
        "Approved exact head with required proof",
    ),
    Path("docs/ai/workflows/merge.md"): (
        "without a separate confirmation pause",
        "defer the merge mutation",
    ),
    Path("docs/ai/workflows/reconcile.md"): (
        "Delete the remote branch only when",
        "Otherwise retain it",
        "leaves affected criteria unchecked",
        "governance knowledge reconciliation",
    ),
    Path("docs/ai/workflows/governance-reconcile.md"): (
        "after every focused PR merge",
        "Governance knowledge reconciliation: no new reusable finding",
        "accepted focused governance Issue",
        "independently reviewed update",
        "do not create a recursive empty Issue",
        "CI runner or Actions signals",
    ),
    Path("docs/ai/knowledge/README.md"): (
        "not an append-only incident ledger",
        "Select one canonical target",
        "accepted focused governance Issue",
        "independently reviewed PR",
        "current focused governance PR",
    ),
    Path("docs/ai/review/inspect.md"): (
        "reusable process or review knowledge candidate",
        "candidate becomes an actionable finding only when",
    ),
    Path("docs/ai/review/verdict.md"): (
        "Reusable governance candidate",
        "not permission for the reviewer",
    ),
    Path("docs/ai/review/setup.md"): (
        "--depth 1",
        "--no-tags",
        "canonical workspace",
    ),
    Path("docs/ai/review/cleanup.md"): (
        "extended-length path handling",
        "temporary path no longer exists",
        "Do not make a second GitHub write",
    ),
    Path(".github/workflows/CI_PLAYBOOK.md"): (
        "thin router",
        "Do not preload every procedure",
        "Select the first matching state",
    ),
    Path("docs/ai/ci/preflight.md"): (
        "keeps baseline and current-head trust separate",
        "Verification-Skip",
        "cold full selection",
        "Local Docker always falls back to Actions",
    ),
    Path("docs/ai/ci/local-rehearsal.md"): (
        "External timeout termination is not verification evidence",
        "does not resolve or invoke the Docker CLI",
    ),
    Path("docs/ai/ci/markdown-only.md"): (
        "machine-qualified exception",
        "absent run is never passing evidence",
        "use normal exact-head Actions proof",
        "Squash merge boundary",
    ),
    Path("docs/ai/ci/post-merge.md"): (
        "after every feature PR merge",
        "no new reusable finding",
        "Revise or add one knowledge leaf",
        "focused playbook-update Issue",
        "Publish a knowledge change only through its focused Issue",
    ),
    Path("docs/ai/ci/failure-triage.md"): (
        "Promote only a new reusable decision rule",
        "Update one canonical knowledge leaf or add one routed leaf",
    ),
    Path("docs/adr/0008-progressive-disclosure-ai-guidance.md"): (
        "Supersedes",
        "ordered first-match selection",
        "exact routed file inventory",
        "ADR-0006 remains historical evidence",
    ),
    Path("docs/adr/0009-reviewed-governance-knowledge-reconciliation.md"): (
        "ADR-0008 introduced progressive-disclosure routing",
        "Reusable governance candidate",
        "one canonical destination",
        "focused governance Issue",
        "independently reviewed PR",
    ),
}

FORBIDDEN_STALE_ROUTING_TEXT = {
    Path("CONTRIBUTING.md"): (
        "[delivery specifications](docs/delivery/) in numeric order",
    ),
    Path("GIT_AGENTS.md"): (
        "Read [the AI collaboration contract](docs/ai/README.md)",
        "accepted ADRs under",
        "accepted delivery specifications under",
        "Read Issue #1 and only the focused Issue",
    ),
    Path("docs/ai/README.md"): (
        "This is the single operating contract",
        "Read [GIT_AGENTS.md] and its required design sources",
        "Issue #1 is the live portfolio ledger",
        "Implementation lifecycle",
    ),
    Path("docs/ai/PR_REVIEW.md"): (
        "accepted ADRs and accepted delivery specifications in numeric order",
        "Delivery Specification 0001, the focused Issue",
    ),
    Path(".github/workflows/CI_PLAYBOOK.md"): (
        "Change-driven first-push checks",
        "Historical evidence ledger",
    ),
}

OWNER_CONFIRMATION_OWNER = Path("docs/ai/workflows/focus.md")
OWNER_CONFIRMATION_HEADING = "## Owner-confirmation STOP"
STOP_HEADING = re.compile(r"(?im)^## [^\r\n]*\bstop\b[^\r\n]*$")
FORBIDDEN_OWNER_CONFIRMATION_PATTERNS = {
    "owner approval gate": re.compile(
        r"(?i)\b(?:explicit owner approval|owner(?:'s)? explicit approval|"
        r"obtain owner approval|owner approval may|owner[- ]approved)\b"
    ),
    "owner authorization gate": re.compile(
        r"(?i)\b(?:explicit owner authorization|owner(?:'s)? exact "
        r"authorization|owner has authorized|only with owner authorization|"
        r"owner (?:explicitly )?authorizes)\b"
    ),
    "owner direction gate": re.compile(
        r"(?i)\b(?:explicit owner direction|owner direction|await owner "
        r"direction)\b"
    ),
    "owner request gate": re.compile(
        r"(?i)\b(?:ask the owner|stop for the owner|await the owner)\b"
    ),
    "owner-only gate": re.compile(r"(?i)\bowner-only\b"),
}

REQUIRED_CI_FAILURE_RUN_IDS = (
    "29639639004",
    "29639776329",
    "29641893290",
    "29666718552",
    "29672537036",
    "29672715519",
    "29673187660",
    "29673641464",
    "29675397127",
    "29675923281",
    "29676215101",
    "30155542598",
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
ROUTED_PUBLIC_SURFACE = frozenset(
    path
    for source, targets in REQUIRED_ROUTE_LINKS.items()
    for path in (source, *targets)
)
PUBLIC_GOVERNANCE_SCAN_FILES = ROUTED_PUBLIC_SURFACE | {
    Path("README.md"),
    Path("CONTRIBUTING.md"),
    Path(".github/workflows/README.md"),
    Path("scripts/README.md"),
    Path("docs/adr/0008-progressive-disclosure-ai-guidance.md"),
}
DESIGN_SELECTION_DIRECTORIES = (
    Path("docs/adr"),
    Path("docs/delivery"),
)
FORBIDDEN_GOVERNANCE_PATTERNS = {
    "Windows absolute path": re.compile(r"(?i)(?<![a-z0-9_])[a-z]:[\\/]"),
    # Reject every multi-segment leading-slash path except the canonical public API
    # route; retain explicit single-segment machine roots such as /etc and /tmp.
    "POSIX absolute path": re.compile(
        r"(?ix)(?<![\w/:<.~])/"
        r"(?:"
        r"(?:etc|home|mnt|opt|private|root|run|srv|tmp|usr|var|volumes|workspace)"
        r"(?:/|\b)[^\s`'\"><\])}]*"
        r"|"
        r"(?!(?:api)(?:/|\b))"
        r"[a-z0-9._~-]+/[^\s`'\"><\])}]+"
        r")"
    ),
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


def design_governance_paths() -> list[Path]:
    return sorted(
        path
        for relative_directory in DESIGN_SELECTION_DIRECTORIES
        for path in (REPOSITORY_ROOT / relative_directory).glob("*.md")
        if path.is_file()
    )


def local_target(raw_target: str) -> str | None:
    target = raw_target.strip().strip("<>").split(maxsplit=1)[0]
    if target.startswith(IGNORED_PREFIXES):
        return None
    return unquote(target.split("#", maxsplit=1)[0])


def resolved_local_links(relative_source: Path) -> set[Path]:
    path = REPOSITORY_ROOT / relative_source
    if not path.is_file():
        return set()

    links: set[Path] = set()
    content = path.read_text(encoding="utf-8")
    for match in MARKDOWN_LINK.finditer(content):
        target = local_target(match.group(1))
        if not target:
            continue
        resolved = (path.parent / target).resolve()
        try:
            links.add(resolved.relative_to(REPOSITORY_ROOT.resolve()))
        except ValueError:
            continue
    return links


def _validate_inventory_and_roles(failures: list[str]) -> list[Path]:
    governance_root = REPOSITORY_ROOT / "docs" / "ai"
    if not governance_root.is_dir():
        failures.append("missing governance directory docs/ai")
        return []

    actual_files = frozenset(
        path.relative_to(governance_root)
        for path in governance_root.rglob("*")
        if path.is_file()
    )
    for unexpected_path in sorted(actual_files - EXPECTED_AI_GUIDANCE_FILES):
        failures.append(
            f"docs/ai contains unexpected file {unexpected_path.as_posix()}"
        )
    for missing_path in sorted(EXPECTED_AI_GUIDANCE_FILES - actual_files):
        failures.append(f"docs/ai is missing required file {missing_path.as_posix()}")

    role_paths = {**ENTRYPOINT_FILE_ROLES, **DOCFORAI_FILE_ROLES}
    for relative_path, expected_role in role_paths.items():
        path = REPOSITORY_ROOT / relative_path
        if not path.is_file():
            continue
        marker = f"<!-- docforai-role: {expected_role} -->"
        content = path.read_text(encoding="utf-8")
        if content.count(marker) != 1:
            failures.append(
                f"{relative_path.as_posix()}: expected one role marker {marker!r}"
            )
        if expected_role in {"procedure", "reference", "knowledge"}:
            if "## Read when" not in content:
                failures.append(f"{relative_path.as_posix()}: missing '## Read when'")
            if "## Next" not in content and "## Return" not in content:
                failures.append(
                    f"{relative_path.as_posix()}: missing next or return transition"
                )

    return sorted(governance_root.rglob("*.md"))


def _validate_rule_ownership(failures: list[str], governance_paths: list[Path]) -> None:
    contents = {
        path.relative_to(REPOSITORY_ROOT): path.read_text(encoding="utf-8")
        for path in governance_paths
    }
    for marker_name, owner in CANONICAL_RULE_OWNERS.items():
        marker = f"<!-- docforai-rule: {marker_name} -->"
        occurrences = [
            (path, content.count(marker))
            for path, content in contents.items()
            if marker in content
        ]
        if occurrences != [(owner, 1)]:
            rendered = (
                ", ".join(f"{path.as_posix()} ({count})" for path, count in occurrences)
                or "none"
            )
            failures.append(
                f"canonical rule {marker_name!r} expected once in "
                f"{owner.as_posix()}, found in {rendered}"
            )


def _validate_routes(failures: list[str]) -> None:
    for source, required_targets in REQUIRED_ROUTE_LINKS.items():
        links = resolved_local_links(source)
        for target in required_targets:
            if target not in links:
                failures.append(
                    f"{source.as_posix()}: missing required route link "
                    f"{target.as_posix()}"
                )
        for target in sorted((links & ROUTED_PUBLIC_SURFACE) - set(required_targets)):
            failures.append(
                f"{source.as_posix()}: contains undeclared route link "
                f"{target.as_posix()}"
            )

    reachable: set[Path] = set()
    pending = deque([Path("GIT_AGENTS.md")])
    while pending:
        source = pending.popleft()
        if source in reachable:
            continue
        reachable.add(source)
        pending.extend(REQUIRED_ROUTE_LINKS.get(source, ()))

    required_reachable_surface = {
        Path("GIT_AGENTS.md"),
        Path("AI_GUIDANCE.md"),
        Path(".github/workflows/CI_PLAYBOOK.md"),
        *DOCFORAI_FILE_ROLES,
    }
    for unreachable in sorted(required_reachable_surface - reachable):
        failures.append(
            f"routed governance file is unreachable: {unreachable.as_posix()}"
        )


def _validate_router_budgets(failures: list[str]) -> None:
    for relative_path, maximum_lines in ROUTER_LINE_BUDGETS.items():
        path = REPOSITORY_ROOT / relative_path
        if not path.is_file():
            continue
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > maximum_lines:
            failures.append(
                f"{relative_path.as_posix()}: router has {line_count} lines, "
                f"budget is {maximum_lines}"
            )


def _validate_ci_failure_knowledge(failures: list[str]) -> None:
    knowledge_root = REPOSITORY_ROOT / "docs" / "ai" / "ci" / "knowledge"
    knowledge_leaves = [
        path.read_text(encoding="utf-8")
        for path in sorted(knowledge_root.glob("*.md"))
        if path.name != "README.md"
    ]
    counts = Counter(
        run_id
        for run_id in REQUIRED_CI_FAILURE_RUN_IDS
        for content in knowledge_leaves
        if run_id in content
    )
    for run_id in REQUIRED_CI_FAILURE_RUN_IDS:
        if counts[run_id] != 1:
            failures.append(
                f"CI failed run {run_id} must appear in exactly one knowledge "
                f"leaf, found {counts[run_id]}"
            )


def _validate_owner_confirmation_boundary(
    failures: list[str], governance_paths: list[Path]
) -> None:
    heading_occurrences: list[tuple[Path, str]] = []
    for path in governance_paths:
        relative_path = path.relative_to(REPOSITORY_ROOT)
        content = path.read_text(encoding="utf-8")
        normalized_content = " ".join(content.split())
        heading_occurrences.extend(
            (relative_path, heading) for heading in STOP_HEADING.findall(content)
        )
        if relative_path == OWNER_CONFIRMATION_OWNER:
            continue
        for label, pattern in FORBIDDEN_OWNER_CONFIRMATION_PATTERNS.items():
            if pattern.search(normalized_content):
                failures.append(
                    f"{relative_path.as_posix()}: contains forbidden {label}; "
                    "owner confirmation is reserved for focused-slice selection"
                )

    expected = [(OWNER_CONFIRMATION_OWNER, OWNER_CONFIRMATION_HEADING)]
    if heading_occurrences != expected:
        rendered = (
            ", ".join(
                f"{path.as_posix()} ({heading})"
                for path, heading in heading_occurrences
            )
            or "none"
        )
        failures.append(
            "owner-confirmation STOP must exist exactly once in "
            f"{OWNER_CONFIRMATION_OWNER.as_posix()}, found {rendered}"
        )


def _validate_public_governance_surface(
    failures: list[str], governance_paths: list[Path]
) -> None:
    for path in governance_paths:
        content = path.read_text(encoding="utf-8")
        for label, pattern in FORBIDDEN_GOVERNANCE_PATTERNS.items():
            if pattern.search(content):
                relative_path = path.relative_to(REPOSITORY_ROOT)
                failures.append(
                    f"{relative_path.as_posix()}: contains forbidden {label}"
                )


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
        normalized_content = " ".join(path.read_text(encoding="utf-8").split())
        for fragment in required_fragments:
            if fragment not in normalized_content:
                failures.append(
                    f"{relative_path.as_posix()}: missing governance invariant "
                    f"{fragment!r}"
                )

    for relative_path, forbidden_fragments in FORBIDDEN_STALE_ROUTING_TEXT.items():
        path = REPOSITORY_ROOT / relative_path
        if not path.is_file():
            continue
        normalized_content = " ".join(path.read_text(encoding="utf-8").split())
        for fragment in forbidden_fragments:
            if fragment in normalized_content:
                failures.append(
                    f"{relative_path.as_posix()}: contains stale routing {fragment!r}"
                )

    ai_paths = _validate_inventory_and_roles(failures)
    governance_paths = sorted(
        {
            REPOSITORY_ROOT / path
            for path in PUBLIC_GOVERNANCE_SCAN_FILES
            if (REPOSITORY_ROOT / path).is_file()
        }
        | set(ai_paths)
        | set(design_governance_paths())
    )

    _validate_rule_ownership(failures, governance_paths)
    _validate_routes(failures)
    _validate_router_budgets(failures)
    _validate_ci_failure_knowledge(failures)
    _validate_owner_confirmation_boundary(failures, governance_paths)
    _validate_public_governance_surface(failures, governance_paths)

    return failures


def main() -> int:
    failures = governance_failures()
    checked_links = 0
    markdown_files = iter_markdown_files()

    for document in markdown_files:
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
        f"Validated {checked_links} local links across {len(markdown_files)} "
        "Markdown files and the routed repository-owned AI governance graph."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
