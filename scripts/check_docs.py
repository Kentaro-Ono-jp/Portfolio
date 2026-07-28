from __future__ import annotations

import os
import re
from collections import Counter, deque
from pathlib import Path
from urllib.parse import unquote


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
MARKDOWN_REFERENCE_LABEL = r"(?:\\.|[^\]]){1,999}"
MARKDOWN_OPTIONAL_REFERENCE_LABEL = r"(?:\\.|[^\]]){0,999}"
MARKDOWN_REFERENCE_DEFINITION = re.compile(
    rf"\[({MARKDOWN_REFERENCE_LABEL})\]:[ \t]*"
    rf"(?:(?:\r\n|\r|\n)[ \t]*(?:>[ \t]*)*)?"
    rf"(?:<([^>\r\n]+)>|([^\s]+))"
)
MARKDOWN_REFERENCE_LINK = re.compile(
    rf"(?<!!)\[({MARKDOWN_REFERENCE_LABEL})\]"
    rf"\[({MARKDOWN_OPTIONAL_REFERENCE_LABEL})\]"
)
MARKDOWN_SHORTCUT_REFERENCE_LINK = re.compile(
    rf"(?<![!\]])\[({MARKDOWN_REFERENCE_LABEL})\](?![ \t]*(?:\(|\[|:))"
)
IGNORED_PREFIXES = ("#", "http://", "https://", "mailto:")

IPS_ROOT = Path("ips-microkernel")
IPS_HUMAN_README = IPS_ROOT / "README.md"
IPS_HUMAN_CONTEXT_MARKER = "<!-- ips-context: human-only -->"
IPS_RUNTIME_DIRECTORIES = (
    Path("selectors"),
    Path("references"),
    Path("procedures"),
    Path("review"),
    Path("ci"),
)
EXPECTED_IPS_TOP_LEVEL_ENTRIES = frozenset(
    {
        "adr",
        "architecture",
        "delivery",
        *(path.as_posix() for path in IPS_RUNTIME_DIRECTORIES),
        "README.md",
        "work-router.md",
    }
)
IPS_ROLE_MARKER = re.compile(r"<!--\s*ips-role:\s*([a-z-]+)\s*-->")
IPS_RUNTIME_MARKER = re.compile(r"<!--\s*ips-(?:role|rule):")
LEGACY_ROLE_OR_RULE_MARKER = re.compile(r"<!--\s*(?:docforai|aios)-(?:role|rule):")

IPS_FILE_ROLES = {
    Path("ips-microkernel/work-router.md"): "router",
    Path("ips-microkernel/review/router.md"): "router",
    Path("ips-microkernel/selectors/governance-knowledge.md"): "selector",
    Path("ips-microkernel/references/authority.md"): "reference",
    Path("ips-microkernel/references/live-state.md"): "reference",
    Path("ips-microkernel/references/public-safety.md"): "reference",
    Path("ips-microkernel/references/evidence.md"): "reference",
    Path("ips-microkernel/references/local-tools.md"): "reference",
    Path("ips-microkernel/procedures/focus.md"): "procedure",
    Path("ips-microkernel/procedures/implement.md"): "procedure",
    Path("ips-microkernel/procedures/publish.md"): "procedure",
    Path("ips-microkernel/procedures/correct.md"): "procedure",
    Path("ips-microkernel/procedures/merge.md"): "procedure",
    Path("ips-microkernel/procedures/reconcile.md"): "procedure",
    Path("ips-microkernel/procedures/governance-reconcile.md"): "procedure",
    Path("ips-microkernel/review/setup.md"): "procedure",
    Path("ips-microkernel/review/inspect.md"): "procedure",
    Path("ips-microkernel/review/verdict.md"): "procedure",
    Path("ips-microkernel/review/cleanup.md"): "procedure",
    Path("ips-microkernel/ci/router.md"): "router",
    Path("ips-microkernel/ci/procedures/preflight.md"): "procedure",
    Path("ips-microkernel/ci/procedures/local-rehearsal.md"): "procedure",
    Path("ips-microkernel/ci/exceptions/markdown-only.md"): "exception",
    Path("ips-microkernel/ci/procedures/failure-triage.md"): "procedure",
    Path("ips-microkernel/ci/procedures/post-merge-reconcile.md"): "procedure",
    Path("ips-microkernel/ci/knowledge/selector.md"): "selector",
    Path("ips-microkernel/ci/knowledge/dependencies.md"): "knowledge",
    Path("ips-microkernel/ci/knowledge/invocation.md"): "knowledge",
    Path("ips-microkernel/ci/knowledge/persistence.md"): "knowledge",
    Path("ips-microkernel/ci/knowledge/isolation.md"): "knowledge",
    Path("ips-microkernel/ci/knowledge/messaging.md"): "knowledge",
    Path("ips-microkernel/ci/knowledge/browser.md"): "knowledge",
    Path("ips-microkernel/ci/knowledge/recovery.md"): "knowledge",
    Path("ips-microkernel/ci/knowledge/evidence.md"): "knowledge",
}
ENTRYPOINT_FILE_ROLES = {
    Path("GIT_AGENTS.md"): "router",
    Path("AI_GUIDANCE.md"): "pointer",
}
EXPECTED_IPS_RUNTIME_FILES = frozenset(
    path.relative_to(IPS_ROOT) for path in IPS_FILE_ROLES
)
REQUIRED_GOVERNANCE_FILES = (
    Path("ips-microkernel/adr/0008-progressive-disclosure-ai-guidance.md"),
    Path("ips-microkernel/adr/0009-reviewed-governance-knowledge-reconciliation.md"),
    Path("ips-microkernel/adr/0010-lossless-review-candidate-capture.md"),
    Path("ips-microkernel/adr/0011-deterministic-shallow-review-diff.md"),
    Path("ips-microkernel/adr/0012-name-aios-nodes-by-runtime-role.md"),
    Path("ips-microkernel/adr/0013-name-ips-microkernel.md"),
    Path("ips-microkernel/adr/index.md"),
    Path("ips-microkernel/architecture/index.md"),
    Path("ips-microkernel/delivery/index.md"),
    IPS_HUMAN_README,
    *ENTRYPOINT_FILE_ROLES,
    *IPS_FILE_ROLES,
)

ROUTING_NODE_LINE_BUDGETS = {
    Path("GIT_AGENTS.md"): 70,
    Path("AI_GUIDANCE.md"): 10,
    Path("ips-microkernel/work-router.md"): 100,
    Path("ips-microkernel/review/router.md"): 65,
    Path("ips-microkernel/selectors/governance-knowledge.md"): 75,
    Path("ips-microkernel/ci/router.md"): 45,
    Path("ips-microkernel/ci/knowledge/selector.md"): 55,
}

CANONICAL_RULE_OWNERS = {
    "progressive-disclosure": Path("ips-microkernel/work-router.md"),
    "review-permission-boundary": Path("ips-microkernel/review/router.md"),
    "governance-knowledge-selection": Path(
        "ips-microkernel/selectors/governance-knowledge.md"
    ),
    "actor-authority": Path("ips-microkernel/references/authority.md"),
    "bounded-live-state": Path("ips-microkernel/references/live-state.md"),
    "public-safety": Path("ips-microkernel/references/public-safety.md"),
    "issue-evidence": Path("ips-microkernel/references/evidence.md"),
    "local-tool-authorization": Path("ips-microkernel/references/local-tools.md"),
    "focus-workflow": Path("ips-microkernel/procedures/focus.md"),
    "implementation-workflow": Path("ips-microkernel/procedures/implement.md"),
    "publication-workflow": Path("ips-microkernel/procedures/publish.md"),
    "correction-workflow": Path("ips-microkernel/procedures/correct.md"),
    "merge-workflow": Path("ips-microkernel/procedures/merge.md"),
    "reconciliation-workflow": Path("ips-microkernel/procedures/reconcile.md"),
    "governance-knowledge-reconciliation": Path(
        "ips-microkernel/procedures/governance-reconcile.md"
    ),
    "review-setup": Path("ips-microkernel/review/setup.md"),
    "review-inspection": Path("ips-microkernel/review/inspect.md"),
    "review-verdict": Path("ips-microkernel/review/verdict.md"),
    "review-cleanup": Path("ips-microkernel/review/cleanup.md"),
    "ci-routing": Path("ips-microkernel/ci/router.md"),
    "ci-preflight": Path("ips-microkernel/ci/procedures/preflight.md"),
    "ci-local-rehearsal": Path("ips-microkernel/ci/procedures/local-rehearsal.md"),
    "ci-markdown-only-exception": Path(
        "ips-microkernel/ci/exceptions/markdown-only.md"
    ),
    "ci-failure-triage": Path("ips-microkernel/ci/procedures/failure-triage.md"),
    "ci-post-merge": Path("ips-microkernel/ci/procedures/post-merge-reconcile.md"),
    "ci-knowledge-selection": Path("ips-microkernel/ci/knowledge/selector.md"),
    "ci-knowledge-dependencies": Path("ips-microkernel/ci/knowledge/dependencies.md"),
    "ci-knowledge-invocation": Path("ips-microkernel/ci/knowledge/invocation.md"),
    "ci-knowledge-persistence": Path("ips-microkernel/ci/knowledge/persistence.md"),
    "ci-knowledge-isolation": Path("ips-microkernel/ci/knowledge/isolation.md"),
    "ci-knowledge-messaging": Path("ips-microkernel/ci/knowledge/messaging.md"),
    "ci-knowledge-browser": Path("ips-microkernel/ci/knowledge/browser.md"),
    "ci-knowledge-recovery": Path("ips-microkernel/ci/knowledge/recovery.md"),
    "ci-knowledge-evidence": Path("ips-microkernel/ci/knowledge/evidence.md"),
}

REQUIRED_ROUTE_LINKS = {
    Path("GIT_AGENTS.md"): (
        Path("AI_GUIDANCE.md"),
        Path("ips-microkernel/work-router.md"),
        Path("ips-microkernel/ci/router.md"),
    ),
    Path("AI_GUIDANCE.md"): (Path("GIT_AGENTS.md"),),
    Path("ips-microkernel/work-router.md"): (
        Path("ips-microkernel/review/router.md"),
        Path("ips-microkernel/references/authority.md"),
        Path("ips-microkernel/references/live-state.md"),
        Path("ips-microkernel/references/local-tools.md"),
        Path("ips-microkernel/procedures/focus.md"),
        Path("ips-microkernel/procedures/implement.md"),
        Path("ips-microkernel/procedures/publish.md"),
        Path("ips-microkernel/procedures/correct.md"),
        Path("ips-microkernel/procedures/merge.md"),
        Path("ips-microkernel/procedures/reconcile.md"),
        Path("ips-microkernel/procedures/governance-reconcile.md"),
        Path("ips-microkernel/ci/router.md"),
        Path("ips-microkernel/delivery/index.md"),
        Path("ips-microkernel/adr/index.md"),
    ),
    Path("ips-microkernel/review/router.md"): (
        Path("ips-microkernel/review/setup.md"),
    ),
    Path("ips-microkernel/procedures/focus.md"): (
        Path("ips-microkernel/delivery/index.md"),
        Path("ips-microkernel/adr/index.md"),
        Path("ips-microkernel/references/live-state.md"),
        Path("ips-microkernel/references/public-safety.md"),
        Path("ips-microkernel/procedures/implement.md"),
    ),
    Path("ips-microkernel/procedures/implement.md"): (
        Path("ips-microkernel/procedures/focus.md"),
        Path("ips-microkernel/references/local-tools.md"),
        Path("ips-microkernel/references/public-safety.md"),
        Path("ips-microkernel/ci/router.md"),
        Path("ips-microkernel/procedures/publish.md"),
    ),
    Path("ips-microkernel/procedures/publish.md"): (
        Path("ips-microkernel/references/live-state.md"),
        Path("ips-microkernel/ci/exceptions/markdown-only.md"),
        Path("ips-microkernel/review/router.md"),
        Path("ips-microkernel/procedures/focus.md"),
        Path("ips-microkernel/procedures/correct.md"),
        Path("ips-microkernel/procedures/merge.md"),
    ),
    Path("ips-microkernel/procedures/correct.md"): (
        Path("ips-microkernel/procedures/focus.md"),
        Path("ips-microkernel/procedures/implement.md"),
        Path("ips-microkernel/procedures/publish.md"),
        Path("ips-microkernel/procedures/merge.md"),
    ),
    Path("ips-microkernel/procedures/merge.md"): (
        Path("ips-microkernel/references/live-state.md"),
        Path("ips-microkernel/ci/exceptions/markdown-only.md"),
        Path("ips-microkernel/ci/router.md"),
        Path("ips-microkernel/procedures/reconcile.md"),
    ),
    Path("ips-microkernel/procedures/reconcile.md"): (
        Path("ips-microkernel/ci/router.md"),
        Path("ips-microkernel/procedures/governance-reconcile.md"),
        Path("ips-microkernel/references/evidence.md"),
        Path("ips-microkernel/work-router.md"),
    ),
    Path("ips-microkernel/procedures/governance-reconcile.md"): (
        Path("ips-microkernel/ci/router.md"),
        Path("ips-microkernel/procedures/focus.md"),
        Path("ips-microkernel/selectors/governance-knowledge.md"),
    ),
    Path("ips-microkernel/selectors/governance-knowledge.md"): (
        Path("ips-microkernel/references/authority.md"),
        Path("ips-microkernel/references/live-state.md"),
        Path("ips-microkernel/references/local-tools.md"),
        Path("ips-microkernel/references/public-safety.md"),
        Path("ips-microkernel/references/evidence.md"),
        Path("ips-microkernel/procedures/focus.md"),
        Path("ips-microkernel/procedures/implement.md"),
        Path("ips-microkernel/procedures/publish.md"),
        Path("ips-microkernel/procedures/correct.md"),
        Path("ips-microkernel/procedures/merge.md"),
        Path("ips-microkernel/procedures/reconcile.md"),
        Path("ips-microkernel/review/setup.md"),
        Path("ips-microkernel/review/inspect.md"),
        Path("ips-microkernel/review/verdict.md"),
        Path("ips-microkernel/review/cleanup.md"),
        Path("ips-microkernel/ci/router.md"),
        Path("ips-microkernel/adr/index.md"),
        Path("ips-microkernel/delivery/index.md"),
    ),
    Path("ips-microkernel/review/setup.md"): (
        Path("ips-microkernel/references/local-tools.md"),
        Path("ips-microkernel/review/inspect.md"),
    ),
    Path("ips-microkernel/review/inspect.md"): (
        Path("ips-microkernel/references/public-safety.md"),
        Path("ips-microkernel/ci/exceptions/markdown-only.md"),
        Path("ips-microkernel/review/verdict.md"),
    ),
    Path("ips-microkernel/review/verdict.md"): (
        Path("ips-microkernel/review/cleanup.md"),
    ),
    Path("ips-microkernel/ci/router.md"): (
        Path("ips-microkernel/ci/procedures/preflight.md"),
        Path("ips-microkernel/ci/procedures/local-rehearsal.md"),
        Path("ips-microkernel/ci/exceptions/markdown-only.md"),
        Path("ips-microkernel/ci/procedures/failure-triage.md"),
        Path("ips-microkernel/ci/procedures/post-merge-reconcile.md"),
        Path("ips-microkernel/ci/knowledge/selector.md"),
        Path("ips-microkernel/work-router.md"),
    ),
    Path("ips-microkernel/ci/procedures/preflight.md"): (
        Path("ips-microkernel/ci/knowledge/selector.md"),
        Path("ips-microkernel/ci/procedures/local-rehearsal.md"),
        Path("ips-microkernel/ci/procedures/failure-triage.md"),
    ),
    Path("ips-microkernel/ci/procedures/local-rehearsal.md"): (
        Path("ips-microkernel/references/local-tools.md"),
    ),
    Path("ips-microkernel/ci/procedures/failure-triage.md"): (
        Path("ips-microkernel/ci/knowledge/selector.md"),
        Path("ips-microkernel/procedures/focus.md"),
    ),
    Path("ips-microkernel/ci/procedures/post-merge-reconcile.md"): (
        Path("ips-microkernel/ci/knowledge/selector.md"),
    ),
    Path("ips-microkernel/ci/knowledge/selector.md"): (
        Path("ips-microkernel/ci/knowledge/dependencies.md"),
        Path("ips-microkernel/ci/knowledge/invocation.md"),
        Path("ips-microkernel/ci/knowledge/persistence.md"),
        Path("ips-microkernel/ci/knowledge/isolation.md"),
        Path("ips-microkernel/ci/knowledge/messaging.md"),
        Path("ips-microkernel/ci/knowledge/browser.md"),
        Path("ips-microkernel/ci/knowledge/recovery.md"),
        Path("ips-microkernel/ci/knowledge/evidence.md"),
    ),
}

GOVERNANCE_KNOWLEDGE_SIGNAL_TARGETS = {
    "actor-authority": Path("ips-microkernel/references/authority.md"),
    "live-state": Path("ips-microkernel/references/live-state.md"),
    "local-tools": Path("ips-microkernel/references/local-tools.md"),
    "public-safety": Path("ips-microkernel/references/public-safety.md"),
    "issue-evidence": Path("ips-microkernel/references/evidence.md"),
    "focus": Path("ips-microkernel/procedures/focus.md"),
    "implementation": Path("ips-microkernel/procedures/implement.md"),
    "publication": Path("ips-microkernel/procedures/publish.md"),
    "correction": Path("ips-microkernel/procedures/correct.md"),
    "merge": Path("ips-microkernel/procedures/merge.md"),
    "reconciliation": Path("ips-microkernel/procedures/reconcile.md"),
    "review-setup": Path("ips-microkernel/review/setup.md"),
    "review-inspection": Path("ips-microkernel/review/inspect.md"),
    "review-verdict": Path("ips-microkernel/review/verdict.md"),
    "review-cleanup": Path("ips-microkernel/review/cleanup.md"),
    "ci": Path("ips-microkernel/ci/router.md"),
    "architecture": Path("ips-microkernel/adr/index.md"),
    "delivery": Path("ips-microkernel/delivery/index.md"),
}
GOVERNANCE_KNOWLEDGE_SIGNAL_FRAGMENTS = {
    "issue-evidence": (
        "Checklist criterion mapping",
        "completion-evidence content",
        "umbrella-gate proof",
    ),
    "reconciliation": (
        "Post-merge sequencing",
        "main fast-forward",
        "branch deletion",
        "task-owned cleanup",
    ),
}

REVIEW_CANDIDATE_CAPTURE_FRAGMENTS = {
    Path("ips-microkernel/review/inspect.md"): (
        "classify every evidenced reusable process or review candidate",
        "Split compound observations into atomic root-cause candidates",
        "retain every candidate for the verdict",
        "Use `none` only when no reusable candidate was discovered",
    ),
    Path("ips-microkernel/review/verdict.md"): (
        "one numbered item for every atomic reusable candidate",
        "`none` is permitted only when no reusable candidate was discovered",
        "never use it as a substitute for a second or later item",
        "every reusable-governance candidate or valid `none`",
    ),
    Path("ips-microkernel/procedures/governance-reconcile.md"): (
        "Expand every numbered candidate item from every verdict",
        "preserve stable source order",
        "Never stop ingestion after the first verdict item",
    ),
}

SHALLOW_REVIEW_DIFF_FRAGMENTS = {
    Path("ips-microkernel/review/router.md"): (
        "Expected full base SHA",
        "Expected full head SHA",
    ),
    Path("ips-microkernel/review/setup.md"): (
        "Resolve the live PR base and head",
        "expected full base and head SHAs",
        "Never infer a missing base",
        "git fetch --no-tags --depth 1 origin <expected-base-sha>",
        "git cat-file -e <expected-base-sha>^{commit}",
        "Do not deepen, unshallow, or search history for a merge base",
    ),
    Path("ips-microkernel/review/inspect.md"): (
        "canonical GitHub PR patch and complete paginated file inventory",
        "git diff --name-status <expected-base-sha> <expected-head-sha>",
        "git diff --binary <expected-base-sha> <expected-head-sha> --",
        "do not require a merge base",
        "never rely on a three-dot comparison as the only complete-diff proof",
        "Require the GitHub and exact endpoint inventories to agree",
        "file or status mismatch is a blocking limitation",
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
    Path("ips-microkernel/work-router.md"): (
        "progressive disclosure",
        "Select the first matching state",
        "Do not read all ADRs or delivery specifications",
        "A loop-back is valid only after state changed",
        "The only owner-confirmation STOP",
        "reusable non-CI process or review knowledge",
    ),
    Path("ips-microkernel/review/router.md"): (
        "Governing tracking Issue URL",
        "Expected full head SHA",
        "The only permitted GitHub write",
        "Do not push",
        "open only the named next state",
        *SHALLOW_REVIEW_DIFF_FRAGMENTS[Path("ips-microkernel/review/router.md")],
    ),
    Path("ips-microkernel/references/authority.md"): (
        "The only owner-confirmation boundary",
        "standing policy",
        "Docker-backed proof runs in GitHub Actions",
        "A Markdown-only skip is machine-qualified",
        "Only proved checklist criteria change state",
        "A remote branch is deleted only after",
        "Public participant",
    ),
    Path("ips-microkernel/references/live-state.md"): (
        "Do not enumerate every branch",
        "Do not infer current PR, Issue, check, or merge state",
        "Deterministic recovery",
    ),
    Path("ips-microkernel/references/evidence.md"): (
        "Completion evidence",
        "umbrella gate",
        "Check only fully proved criteria",
        "independent reviewer never edits Issue checklists",
    ),
    Path("ips-microkernel/references/local-tools.md"): (
        "Do not request elevated privileges",
        "route Docker-backed or environment-dependent proof to GitHub Actions",
    ),
    Path("ips-microkernel/procedures/publish.md"): (
        "machine-qualified Markdown-only CI exception",
        "Approved exact head with required proof",
    ),
    Path("ips-microkernel/procedures/merge.md"): (
        "without a separate confirmation pause",
        "defer the merge mutation",
    ),
    Path("ips-microkernel/procedures/reconcile.md"): (
        "Delete the remote branch only when",
        "Otherwise retain it",
        "leaves affected criteria unchecked",
        "governance knowledge reconciliation",
    ),
    Path("ips-microkernel/procedures/governance-reconcile.md"): (
        "after every focused PR merge",
        "Governance knowledge reconciliation: no new reusable finding",
        "accepted focused governance Issue",
        "independently reviewed update",
        "do not create a recursive empty Issue",
        "CI runner or Actions signals",
        "ordered candidate queue",
        "For each queued candidate",
        "return to step 4 for the next queued candidate",
        "Only after the queue is exhausted",
        *REVIEW_CANDIDATE_CAPTURE_FRAGMENTS[
            Path("ips-microkernel/procedures/governance-reconcile.md")
        ],
    ),
    Path("ips-microkernel/selectors/governance-knowledge.md"): (
        "not an append-only incident ledger",
        "Select one canonical target",
        "accepted focused governance Issue",
        "independently reviewed PR",
        "current focused governance PR",
        "Rows are ordered precedence",
        "split it into atomic candidates",
        "never assign one candidate to two targets",
    ),
    Path("ips-microkernel/review/inspect.md"): (
        *REVIEW_CANDIDATE_CAPTURE_FRAGMENTS[Path("ips-microkernel/review/inspect.md")],
        *SHALLOW_REVIEW_DIFF_FRAGMENTS[Path("ips-microkernel/review/inspect.md")],
        "candidate becomes an actionable finding only when",
    ),
    Path("ips-microkernel/review/verdict.md"): (
        "Reusable governance candidate",
        "not permission for the reviewer",
        *REVIEW_CANDIDATE_CAPTURE_FRAGMENTS[Path("ips-microkernel/review/verdict.md")],
    ),
    Path("ips-microkernel/review/setup.md"): (
        "--depth 1",
        "--no-tags",
        "canonical workspace",
        *SHALLOW_REVIEW_DIFF_FRAGMENTS[Path("ips-microkernel/review/setup.md")],
    ),
    Path("ips-microkernel/review/cleanup.md"): (
        "extended-length path handling",
        "temporary path no longer exists",
        "Do not make a second GitHub write",
    ),
    Path("ips-microkernel/ci/router.md"): (
        "thin router",
        "Do not preload every procedure",
        "Select the first matching state",
    ),
    Path("ips-microkernel/ci/procedures/preflight.md"): (
        "keeps baseline and current-head trust separate",
        "Verification-Skip",
        "cold full selection",
        "Local Docker always falls back to Actions",
    ),
    Path("ips-microkernel/ci/procedures/local-rehearsal.md"): (
        "External timeout termination is not verification evidence",
        "does not resolve or invoke the Docker CLI",
    ),
    Path("ips-microkernel/ci/exceptions/markdown-only.md"): (
        "machine-qualified exception",
        "absent run is never passing evidence",
        "use normal exact-head Actions proof",
        "Squash merge boundary",
    ),
    Path("ips-microkernel/ci/procedures/post-merge-reconcile.md"): (
        "after every feature PR merge",
        "no new reusable finding",
        "Revise or add one knowledge leaf",
        "focused playbook-update Issue",
        "Publish a knowledge change only through its focused Issue",
    ),
    Path("ips-microkernel/ci/procedures/failure-triage.md"): (
        "Promote only a new reusable decision rule",
        "Update one canonical knowledge leaf or add one routed leaf",
    ),
    Path("ips-microkernel/adr/0008-progressive-disclosure-ai-guidance.md"): (
        "Supersedes",
        "ordered first-match selection",
        "exact routed file inventory",
        "ADR-0006 remains historical evidence",
    ),
    Path("ips-microkernel/adr/0009-reviewed-governance-knowledge-reconciliation.md"): (
        "ADR-0008 introduced progressive-disclosure routing",
        "Reusable governance candidate",
        "one canonical destination",
        "focused governance Issue",
        "independently reviewed PR",
        "ordered candidate queue",
        "representative ambiguity",
    ),
    Path("ips-microkernel/adr/0010-lossless-review-candidate-capture.md"): (
        "ADR-0009 established a reviewed write path",
        "exactly one `Reusable governance candidate` section",
        "one item for every atomic candidate",
        "expands every numbered candidate item from every verdict",
        "singular-only review capture",
        "first-item-only regression",
    ),
    Path("ips-microkernel/adr/0011-deterministic-shallow-review-diff.md"): (
        "ADR-0010",
        "expected full base SHA",
        "exact base commit object",
        "canonical GitHub PR patch",
        "git diff <expected-base-sha> <expected-head-sha>",
        "does not require a merge base",
        "Require inventory agreement",
    ),
    Path("ips-microkernel/adr/0012-name-aios-nodes-by-runtime-role.md"): (
        "The complete top-level `docs/` tree moves to `aios/`",
        "Every AIOS runtime node declares exactly one machine-readable role",
        "`router`",
        "`selector`",
        "`procedure`",
        "`reference`",
        "`knowledge`",
        "`exception`",
        "Runtime filenames and directories encode their role",
        "Accepted ADR prose remains immutable evidence",
    ),
    Path("ips-microkernel/adr/0013-name-ips-microkernel.md"): (
        "intentional Progressive-disclosure System Microkernel",
        "`ips-microkernel/README.md` is human-only",
        "runtime governance graph",
        "legacy `aios/` root",
        "ADR-0012 remains immutable historical evidence",
    ),
    IPS_HUMAN_README: (
        "This page explains the architecture; it does not participate in its runtime",
        "intentional Progressive-disclosure System Microkernel",
        "Not reading is a design decision",
        "Reprogramming, differentiation, and expression",
        "AIOS became the iPS Microkernel",
        "## 日本語",
        "読まないことは設計判断である",
        "再プログラム、分化、発現",
        "その結果、AIOSはiPS Microkernelとなった",
    ),
}

FORBIDDEN_STALE_ROUTING_TEXT = {
    Path("CONTRIBUTING.md"): (
        "[delivery specifications](ips-microkernel/delivery/) in numeric order",
    ),
    Path("GIT_AGENTS.md"): (
        "Read [the AI collaboration contract](ips-microkernel/work-router.md)",
        "accepted ADRs under",
        "accepted delivery specifications under",
        "Read Issue #1 and only the focused Issue",
    ),
    Path("ips-microkernel/work-router.md"): (
        "This is the single operating contract",
        "Read [GIT_AGENTS.md] and its required design sources",
        "Issue #1 is the live portfolio ledger",
        "Implementation lifecycle",
    ),
    Path("ips-microkernel/review/router.md"): (
        "accepted ADRs and accepted delivery specifications in numeric order",
        "Delivery Specification 0001, the focused Issue",
    ),
    Path("ips-microkernel/ci/router.md"): (
        "Change-driven first-push checks",
        "Historical evidence ledger",
    ),
}

OWNER_CONFIRMATION_OWNER = Path("ips-microkernel/procedures/focus.md")
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
    IPS_HUMAN_README,
    Path("ips-microkernel/adr/0008-progressive-disclosure-ai-guidance.md"),
}
DESIGN_SELECTION_DIRECTORIES = (
    Path("ips-microkernel/adr"),
    Path("ips-microkernel/delivery"),
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


def _normalize_reference_label(label: str) -> str:
    return " ".join(label.split()).casefold()


def markdown_link_targets(content: str) -> list[str]:
    targets = [match.group(1) for match in MARKDOWN_LINK.finditer(content)]
    definitions: dict[str, str] = {}
    for match in MARKDOWN_REFERENCE_DEFINITION.finditer(content):
        label = _normalize_reference_label(match.group(1))
        definitions.setdefault(label, match.group(2) or match.group(3))

    for match in MARKDOWN_REFERENCE_LINK.finditer(content):
        label = match.group(2) or match.group(1)
        target = definitions.get(_normalize_reference_label(label))
        if target is not None:
            targets.append(target)

    for match in MARKDOWN_SHORTCUT_REFERENCE_LINK.finditer(content):
        target = definitions.get(_normalize_reference_label(match.group(1)))
        if target is not None:
            targets.append(target)

    return targets


def resolved_local_links(relative_source: Path) -> set[Path]:
    path = REPOSITORY_ROOT / relative_source
    if not path.is_file():
        return set()

    links: set[Path] = set()
    content = path.read_text(encoding="utf-8")
    for raw_target in markdown_link_targets(content):
        target = local_target(raw_target)
        if not target:
            continue
        resolved = (path.parent / target).resolve()
        try:
            links.add(resolved.relative_to(REPOSITORY_ROOT.resolve()))
        except ValueError:
            continue
    return links


def _validate_governance_knowledge_selector(failures: list[str]) -> None:
    relative_path = Path("ips-microkernel/selectors/governance-knowledge.md")
    path = REPOSITORY_ROOT / relative_path
    if not path.is_file():
        return

    rows: list[tuple[str, str, Path]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        stripped = line.strip()
        if not stripped.startswith("| `"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) != 3:
            failures.append(
                f"{relative_path.as_posix()}:{line_number}: malformed signal row"
            )
            continue
        key = cells[0].strip("`")
        links = list(MARKDOWN_LINK.finditer(cells[2]))
        if len(links) != 1:
            failures.append(
                f"{relative_path.as_posix()}:{line_number}: signal {key!r} "
                "must have exactly one canonical target link"
            )
            continue
        target = local_target(links[0].group(1))
        if not target:
            failures.append(
                f"{relative_path.as_posix()}:{line_number}: signal {key!r} "
                "must use one local canonical target"
            )
            continue
        resolved = (path.parent / target).resolve()
        try:
            relative_target = resolved.relative_to(REPOSITORY_ROOT.resolve())
        except ValueError:
            failures.append(
                f"{relative_path.as_posix()}:{line_number}: signal {key!r} "
                "target escapes the repository"
            )
            continue
        rows.append((key, cells[1], relative_target))

    expected_keys = list(GOVERNANCE_KNOWLEDGE_SIGNAL_TARGETS)
    actual_keys = [key for key, _signal, _target in rows]
    if actual_keys != expected_keys:
        failures.append(
            f"{relative_path.as_posix()}: signal keys must be unique and in "
            f"declared precedence order; expected {expected_keys}, found {actual_keys}"
        )

    for key, expected_target in GOVERNANCE_KNOWLEDGE_SIGNAL_TARGETS.items():
        matches = [
            (signal, target) for actual_key, signal, target in rows if actual_key == key
        ]
        if len(matches) != 1 or matches[0][1] != expected_target:
            rendered = (
                ", ".join(target.as_posix() for _signal, target in matches) or "none"
            )
            failures.append(
                f"{relative_path.as_posix()}: signal {key!r} must map exactly "
                f"once to {expected_target.as_posix()}, found {rendered}"
            )
            continue
        signal = matches[0][0]
        for fragment in GOVERNANCE_KNOWLEDGE_SIGNAL_FRAGMENTS.get(key, ()):
            if fragment not in signal:
                failures.append(
                    f"{relative_path.as_posix()}: signal {key!r} is missing "
                    f"disambiguating text {fragment!r}"
                )


def _validate_review_candidate_capture(failures: list[str]) -> None:
    for relative_path, required_fragments in REVIEW_CANDIDATE_CAPTURE_FRAGMENTS.items():
        path = REPOSITORY_ROOT / relative_path
        if not path.is_file():
            continue
        normalized_content = " ".join(path.read_text(encoding="utf-8").split())
        for fragment in required_fragments:
            if fragment not in normalized_content:
                failures.append(
                    f"{relative_path.as_posix()}: missing lossless review-candidate "
                    f"capture invariant {fragment!r}"
                )

    verdict_path = REPOSITORY_ROOT / "ips-microkernel/review/verdict.md"
    if not verdict_path.is_file():
        return
    verdict = verdict_path.read_text(encoding="utf-8")
    candidate_heading = "### Reusable governance candidate"
    verification_heading = "### Verification"
    if verdict.count(candidate_heading) != 1:
        failures.append(
            "ips-microkernel/review/verdict.md: must contain exactly one reusable "
            "governance candidate section"
        )
        return
    candidate_section = verdict.split(candidate_heading, maxsplit=1)[1]
    if verification_heading not in candidate_section:
        failures.append(
            "ips-microkernel/review/verdict.md: candidate section must precede verification"
        )
        return
    candidate_section = candidate_section.split(verification_heading, maxsplit=1)[0]
    for item_number in (1, 2):
        item = re.compile(
            rf"(?m)^{item_number}\. \*\*Signal:\*\* .+ \*\*Evidence:\*\* .+$"
        )
        if not item.search(candidate_section):
            failures.append(
                "ips-microkernel/review/verdict.md: candidate template must demonstrate "
                f"ordered atomic item {item_number} with signal and evidence"
            )


def _validate_shallow_review_diff_contract(failures: list[str]) -> None:
    for relative_path, required_fragments in SHALLOW_REVIEW_DIFF_FRAGMENTS.items():
        path = REPOSITORY_ROOT / relative_path
        if not path.is_file():
            continue
        normalized_content = " ".join(path.read_text(encoding="utf-8").split())
        for fragment in required_fragments:
            if fragment not in normalized_content:
                failures.append(
                    f"{relative_path.as_posix()}: missing deterministic shallow-review "
                    f"diff invariant {fragment!r}"
                )


def _validate_inventory_and_roles(failures: list[str]) -> list[Path]:
    ips_root = REPOSITORY_ROOT / IPS_ROOT
    if not ips_root.is_dir():
        failures.append("missing iPS Microkernel directory ips-microkernel")
        return []

    actual_top_level_entries = frozenset(
        path.name
        for path in ips_root.iterdir()
        if path.is_file()
        or (path.is_dir() and any(child.is_file() for child in path.rglob("*")))
    )
    for unexpected_name in sorted(
        actual_top_level_entries - EXPECTED_IPS_TOP_LEVEL_ENTRIES
    ):
        failures.append(
            f"iPS Microkernel contains unexpected top-level entry {unexpected_name}"
        )
    for missing_name in sorted(
        EXPECTED_IPS_TOP_LEVEL_ENTRIES - actual_top_level_entries
    ):
        failures.append(
            f"iPS Microkernel is missing required top-level entry {missing_name}"
        )

    runtime_paths = [
        path
        for path in ips_root.glob("*.md")
        if path.relative_to(REPOSITORY_ROOT) != IPS_HUMAN_README
    ]
    for relative_directory in IPS_RUNTIME_DIRECTORIES:
        runtime_directory = ips_root / relative_directory
        if runtime_directory.is_dir():
            runtime_paths.extend(
                path for path in runtime_directory.rglob("*") if path.is_file()
            )
    actual_files = frozenset(path.relative_to(ips_root) for path in runtime_paths)
    for unexpected_path in sorted(actual_files - EXPECTED_IPS_RUNTIME_FILES):
        failures.append(
            "iPS Microkernel runtime contains unexpected file "
            f"{unexpected_path.as_posix()}"
        )
    for missing_path in sorted(EXPECTED_IPS_RUNTIME_FILES - actual_files):
        failures.append(
            "iPS Microkernel runtime is missing required file "
            f"{missing_path.as_posix()}"
        )

    role_paths = {**ENTRYPOINT_FILE_ROLES, **IPS_FILE_ROLES}
    declared_roles_by_path: dict[Path, list[str]] = {}
    for markdown_path in iter_markdown_files():
        declared_roles = IPS_ROLE_MARKER.findall(
            markdown_path.read_text(encoding="utf-8")
        )
        if declared_roles:
            declared_roles_by_path[markdown_path.relative_to(REPOSITORY_ROOT)] = (
                declared_roles
            )
    for unexpected_path in sorted(declared_roles_by_path.keys() - role_paths.keys()):
        failures.append(
            f"{unexpected_path.as_posix()}: iPS role markers are forbidden "
            "outside declared role-bearing paths; found "
            f"{declared_roles_by_path[unexpected_path]!r}"
        )

    for relative_path, expected_role in role_paths.items():
        path = REPOSITORY_ROOT / relative_path
        if not path.is_file():
            continue
        marker = f"<!-- ips-role: {expected_role} -->"
        content = path.read_text(encoding="utf-8")
        declared_roles = declared_roles_by_path.get(relative_path, [])
        if declared_roles != [expected_role]:
            failures.append(
                f"{relative_path.as_posix()}: expected exactly one role marker "
                f"{marker!r}, found {declared_roles!r}"
            )
        if relative_path in IPS_FILE_ROLES:
            runtime_path = relative_path.relative_to(IPS_ROOT)
            inferred_role = _role_for_ips_runtime_path(runtime_path)
            if inferred_role is None:
                failures.append(
                    f"{relative_path.as_posix()}: path has no valid iPS runtime role"
                )
            elif inferred_role != expected_role:
                failures.append(
                    f"{relative_path.as_posix()}: path implies role {inferred_role!r}, "
                    f"inventory declares {expected_role!r}"
                )
            if len(declared_roles) == 1 and declared_roles[0] != inferred_role:
                failures.append(
                    f"{relative_path.as_posix()}: declared role "
                    f"{declared_roles[0]!r} disagrees with path role "
                    f"{inferred_role!r}"
                )
        if expected_role in {"procedure", "reference", "knowledge", "exception"}:
            if "## Read when" not in content:
                failures.append(f"{relative_path.as_posix()}: missing '## Read when'")
            if "## Next" not in content and "## Return" not in content:
                failures.append(
                    f"{relative_path.as_posix()}: missing next or return transition"
                )

    return sorted(path for path in runtime_paths if path.suffix == ".md")


def _role_for_ips_runtime_path(relative_path: Path) -> str | None:
    parts = relative_path.parts
    if relative_path == Path("work-router.md") or relative_path.name == "router.md":
        return "router"
    if parts[0] == "selectors" or relative_path.name == "selector.md":
        return "selector"
    if parts[0] == "references":
        return "reference"
    if "exceptions" in parts:
        return "exception"
    if "knowledge" in parts:
        return "knowledge"
    if "procedures" in parts or (
        parts[0] == "review" and relative_path.name != "router.md"
    ):
        return "procedure"
    return None


def _validate_legacy_governance_layout(failures: list[str]) -> None:
    for relative_path in (
        Path("aios"),
        Path("docs"),
        Path(".github/workflows/CI_PLAYBOOK.md"),
    ):
        if (REPOSITORY_ROOT / relative_path).exists():
            failures.append(
                f"legacy governance path must not exist: {relative_path.as_posix()}"
            )

    legacy_runtime_root = REPOSITORY_ROOT / "ips-microkernel" / "ai"
    if legacy_runtime_root.is_dir() and any(
        path.is_file() for path in legacy_runtime_root.rglob("*")
    ):
        failures.append("legacy governance path must not exist: ips-microkernel/ai")

    for path in iter_markdown_files():
        if LEGACY_ROLE_OR_RULE_MARKER.search(path.read_text(encoding="utf-8")):
            relative_path = path.relative_to(REPOSITORY_ROOT)
            failures.append(
                f"{relative_path.as_posix()}: contains a legacy DocForAI or AIOS marker"
            )

    ips_root = REPOSITORY_ROOT / IPS_ROOT
    for relative_directory in IPS_RUNTIME_DIRECTORIES:
        runtime_directory = ips_root / relative_directory
        if not runtime_directory.is_dir():
            continue
        for readme in runtime_directory.rglob("README.md"):
            failures.append(
                f"{readme.relative_to(REPOSITORY_ROOT).as_posix()}: "
                "runtime README.md must use a role-expressive filename"
            )


def _validate_human_only_readme(failures: list[str]) -> None:
    readme = REPOSITORY_ROOT / IPS_HUMAN_README
    if not readme.is_file():
        return

    content = readme.read_text(encoding="utf-8")
    if content.count(IPS_HUMAN_CONTEXT_MARKER) != 1:
        failures.append(
            f"{IPS_HUMAN_README.as_posix()}: expected exactly one human-only "
            f"context marker {IPS_HUMAN_CONTEXT_MARKER!r}"
        )
    if IPS_RUNTIME_MARKER.search(content):
        failures.append(
            f"{IPS_HUMAN_README.as_posix()}: human-only README must not declare "
            "an iPS runtime role or rule"
        )

    runtime_surface = {
        *ENTRYPOINT_FILE_ROLES,
        *IPS_FILE_ROLES,
        *ROUTED_PUBLIC_SURFACE,
    }
    if IPS_HUMAN_README in runtime_surface:
        failures.append(
            f"{IPS_HUMAN_README.as_posix()}: human-only README must not be part "
            "of the runtime governance graph"
        )

    allowed_inbound_sources = {Path("README.md")}
    for markdown_path in iter_markdown_files():
        source = markdown_path.relative_to(REPOSITORY_ROOT)
        if source == IPS_HUMAN_README:
            continue
        if IPS_HUMAN_README not in resolved_local_links(source):
            continue
        if source not in allowed_inbound_sources:
            failures.append(
                f"{source.as_posix()}: human-only README may be linked only by "
                "the repository root README"
            )

    if IPS_HUMAN_README not in resolved_local_links(Path("README.md")):
        failures.append(
            f"README.md: missing human navigation link to {IPS_HUMAN_README.as_posix()}"
        )


def _validate_rule_ownership(failures: list[str], governance_paths: list[Path]) -> None:
    contents = {
        path.relative_to(REPOSITORY_ROOT): path.read_text(encoding="utf-8")
        for path in governance_paths
    }
    for marker_name, owner in CANONICAL_RULE_OWNERS.items():
        marker = f"<!-- ips-rule: {marker_name} -->"
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
        *IPS_FILE_ROLES,
    }
    for unreachable in sorted(required_reachable_surface - reachable):
        failures.append(
            f"routed governance file is unreachable: {unreachable.as_posix()}"
        )


def _validate_routing_node_budgets(failures: list[str]) -> None:
    for relative_path, maximum_lines in ROUTING_NODE_LINE_BUDGETS.items():
        path = REPOSITORY_ROOT / relative_path
        if not path.is_file():
            continue
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > maximum_lines:
            failures.append(
                f"{relative_path.as_posix()}: routing node has {line_count} lines, "
                f"budget is {maximum_lines}"
            )


def _validate_ci_failure_knowledge(failures: list[str]) -> None:
    knowledge_root = REPOSITORY_ROOT / "ips-microkernel" / "ci" / "knowledge"
    knowledge_leaves = [
        path.read_text(encoding="utf-8")
        for path in sorted(knowledge_root.glob("*.md"))
        if path.name != "selector.md"
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

    _validate_legacy_governance_layout(failures)
    _validate_human_only_readme(failures)

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

    ips_paths = _validate_inventory_and_roles(failures)
    governance_paths = sorted(
        {
            REPOSITORY_ROOT / path
            for path in PUBLIC_GOVERNANCE_SCAN_FILES
            if (REPOSITORY_ROOT / path).is_file()
        }
        | set(ips_paths)
        | set(design_governance_paths())
    )

    _validate_rule_ownership(failures, governance_paths)
    _validate_routes(failures)
    _validate_governance_knowledge_selector(failures)
    _validate_review_candidate_capture(failures)
    _validate_shallow_review_diff_contract(failures)
    _validate_routing_node_budgets(failures)
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
        for raw_target in markdown_link_targets(content):
            target = local_target(raw_target)
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
        "Markdown files and the routed iPS Microkernel governance graph."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
