from __future__ import annotations

import os
import re
from collections import Counter, deque
from html import unescape
from pathlib import Path
from urllib.parse import unquote, urlsplit


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
MARKDOWN_HTML_ANCHOR = re.compile(
    r"""(?is)<a\b[^>]*?\bhref\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))"""
)
MARKDOWN_BACKSLASH_ESCAPE = re.compile(
    r"""\\([!"#$%&'()*+,\-./:;<=>?@\[\]\\^_`{|}~])"""
)
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
IPS_HUMAN_CONTEXT_MARKER = "<!-- ips-context: human-only -->"
IPS_RUNTIME_DIRECTORIES = (
    Path("selectors"),
    Path("references"),
    Path("procedures"),
    Path("knowledge"),
    Path("review"),
    Path("ci"),
)
EXPECTED_IPS_TOP_LEVEL_ENTRIES = frozenset(
    {
        "adr",
        "architecture",
        "delivery",
        *(path.as_posix() for path in IPS_RUNTIME_DIRECTORIES),
        "work-router.md",
    }
)
IPS_ROLE_MARKER = re.compile(r"<!--\s*ips-role:\s*([a-z-]+)\s*-->")
IPS_RUNTIME_MARKER = re.compile(r"<!--\s*ips-(?:role|rule):")
LEGACY_ROLE_OR_RULE_MARKER = re.compile(r"<!--\s*(?:docforai|aios)-(?:role|rule):")
STAGE_A_RECORD_PATH = re.compile(r"^knowledge/corrections/pr-\d{4}\.md$")

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
    Path("ips-microkernel/procedures/adjudicate.md"): "procedure",
    Path("ips-microkernel/procedures/curate-knowledge.md"): "procedure",
    Path("ips-microkernel/procedures/correct.md"): "procedure",
    Path("ips-microkernel/procedures/merge.md"): "procedure",
    Path("ips-microkernel/procedures/reconcile.md"): "procedure",
    Path("ips-microkernel/procedures/governance-reconcile.md"): "procedure",
    Path("ips-microkernel/knowledge/correction-ledger.md"): "knowledge",
    Path("ips-microkernel/knowledge/behavior.md"): "knowledge",
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
    Path("ips-microkernel/ci/knowledge/identity.md"): "knowledge",
    Path("ips-microkernel/ci/knowledge/contracts.md"): "knowledge",
    Path("ips-microkernel/ci/knowledge/framework-runtime.md"): "knowledge",
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
    Path("ips-microkernel/adr/0014-adopt-revisitable-state-governance.md"),
    Path("ips-microkernel/adr/0015-hide-the-human-origin-narrative.md"),
    Path("ips-microkernel/adr/0016-adjudicate-review-findings-before-correction.md"),
    Path("ips-microkernel/adr/0017-delegate-evidence-bound-knowledge-curation.md"),
    Path(
        "ips-microkernel/adr/0018-bound-post-correction-careless-mistake-writeback.md"
    ),
    Path(
        "ips-microkernel/adr/0019-separate-correction-records-from-pre-review-checks.md"
    ),
    Path("ips-microkernel/adr/index.md"),
    Path("ips-microkernel/architecture/index.md"),
    Path("ips-microkernel/delivery/index.md"),
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
    Path("ips-microkernel/ci/knowledge/selector.md"): 65,
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
    "review-adjudication": Path("ips-microkernel/procedures/adjudicate.md"),
    "knowledge-curation": Path("ips-microkernel/procedures/curate-knowledge.md"),
    "correction-workflow": Path("ips-microkernel/procedures/correct.md"),
    "merge-workflow": Path("ips-microkernel/procedures/merge.md"),
    "reconciliation-workflow": Path("ips-microkernel/procedures/reconcile.md"),
    "governance-knowledge-reconciliation": Path(
        "ips-microkernel/procedures/governance-reconcile.md"
    ),
    "implementation-correction-ledger": Path(
        "ips-microkernel/knowledge/correction-ledger.md"
    ),
    "stage-b-pre-review-checklist": Path("ips-microkernel/knowledge/behavior.md"),
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
    "ci-knowledge-identity": Path("ips-microkernel/ci/knowledge/identity.md"),
    "ci-knowledge-contracts": Path("ips-microkernel/ci/knowledge/contracts.md"),
    "ci-knowledge-framework-runtime": Path(
        "ips-microkernel/ci/knowledge/framework-runtime.md"
    ),
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
        Path("ips-microkernel/procedures/adjudicate.md"),
        Path("ips-microkernel/procedures/curate-knowledge.md"),
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
        Path("ips-microkernel/procedures/publish.md"),
    ),
    Path("ips-microkernel/procedures/publish.md"): (
        Path("ips-microkernel/references/live-state.md"),
        Path("ips-microkernel/knowledge/behavior.md"),
        Path("ips-microkernel/ci/router.md"),
        Path("ips-microkernel/ci/exceptions/markdown-only.md"),
        Path("ips-microkernel/review/router.md"),
        Path("ips-microkernel/procedures/focus.md"),
        Path("ips-microkernel/procedures/adjudicate.md"),
        Path("ips-microkernel/procedures/curate-knowledge.md"),
        Path("ips-microkernel/procedures/correct.md"),
        Path("ips-microkernel/procedures/merge.md"),
    ),
    Path("ips-microkernel/procedures/adjudicate.md"): (
        Path("ips-microkernel/references/live-state.md"),
        Path("ips-microkernel/procedures/focus.md"),
        Path("ips-microkernel/procedures/curate-knowledge.md"),
        Path("ips-microkernel/procedures/correct.md"),
        Path("ips-microkernel/procedures/merge.md"),
    ),
    Path("ips-microkernel/procedures/curate-knowledge.md"): (
        Path("ips-microkernel/references/live-state.md"),
        Path("ips-microkernel/ci/router.md"),
        Path("ips-microkernel/procedures/focus.md"),
        Path("ips-microkernel/selectors/governance-knowledge.md"),
        Path("ips-microkernel/procedures/implement.md"),
    ),
    Path("ips-microkernel/procedures/correct.md"): (
        Path("ips-microkernel/procedures/focus.md"),
        Path("ips-microkernel/procedures/implement.md"),
        Path("ips-microkernel/procedures/publish.md"),
        Path("ips-microkernel/procedures/adjudicate.md"),
        Path("ips-microkernel/procedures/curate-knowledge.md"),
        Path("ips-microkernel/procedures/merge.md"),
        Path("ips-microkernel/knowledge/correction-ledger.md"),
        Path("ips-microkernel/knowledge/behavior.md"),
    ),
    Path("ips-microkernel/procedures/merge.md"): (
        Path("ips-microkernel/references/live-state.md"),
        Path("ips-microkernel/ci/exceptions/markdown-only.md"),
        Path("ips-microkernel/ci/router.md"),
        Path("ips-microkernel/procedures/adjudicate.md"),
        Path("ips-microkernel/procedures/curate-knowledge.md"),
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
        Path("ips-microkernel/procedures/curate-knowledge.md"),
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
        Path("ips-microkernel/procedures/adjudicate.md"),
        Path("ips-microkernel/procedures/curate-knowledge.md"),
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
        Path("ips-microkernel/knowledge/correction-ledger.md"),
    ),
    Path("ips-microkernel/ci/procedures/post-merge-reconcile.md"): (),
    Path("ips-microkernel/ci/knowledge/selector.md"): (
        Path("ips-microkernel/ci/knowledge/dependencies.md"),
        Path("ips-microkernel/ci/knowledge/invocation.md"),
        Path("ips-microkernel/ci/knowledge/persistence.md"),
        Path("ips-microkernel/ci/knowledge/isolation.md"),
        Path("ips-microkernel/ci/knowledge/messaging.md"),
        Path("ips-microkernel/ci/knowledge/browser.md"),
        Path("ips-microkernel/ci/knowledge/recovery.md"),
        Path("ips-microkernel/ci/knowledge/evidence.md"),
        Path("ips-microkernel/ci/knowledge/identity.md"),
        Path("ips-microkernel/ci/knowledge/contracts.md"),
        Path("ips-microkernel/ci/knowledge/framework-runtime.md"),
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
    "adjudication": Path("ips-microkernel/procedures/adjudicate.md"),
    "curation": Path("ips-microkernel/procedures/curate-knowledge.md"),
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
    "adjudication": (
        "Review-finding disposition",
        "human-scale lenses",
        "adjudicated-RC routing",
    ),
    "curation": (
        "Reusable-candidate evidence threshold",
        "promotion timing",
        "deferred recovery",
    ),
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
    Path("ips-microkernel/procedures/curate-knowledge.md"): (
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

REVIEW_ADJUDICATION_FRAGMENTS = {
    Path("ips-microkernel/work-router.md"): (
        "`Changes requested` verdict contains findings whose disposition is incomplete",
        "[review finding adjudication](procedures/adjudicate.md)",
        "fully adjudicated exact head with zero required corrections",
    ),
    Path("ips-microkernel/references/authority.md"): (
        "Review Adjudicator",
        "distinct runtime role",
        "does not silently adjudicate while implementing",
        "fully adjudicated",
    ),
    Path("ips-microkernel/references/live-state.md"): (
        "| Adjudication | Verdict SHA and URL",
        "complete zero-required-correction adjudication",
    ),
    Path("ips-microkernel/procedures/publish.md"): (
        "`Changes requested` with incomplete finding disposition",
        "[adjudicate](adjudicate.md)",
        "fully adjudicated exact head with zero required corrections",
    ),
    Path("ips-microkernel/procedures/adjudicate.md"): (
        "distinct runtime role",
        "Do not modify implementation",
        "materially breaks the Issue-defined accepted product design at Critical or High impact",
        "human discoverability and bounded recoverability",
        "external technical explanation cost",
        "material product-quality effect",
        "Do not use a numeric score",
        "append one adjudication checkpoint to the focused Issue",
        "exact reviewed head and stable real-verdict URL",
        "reviewer severity and adjudicated actual impact",
        "`required-correction`",
        "`accepted-residual`",
        "`non-material`",
        "Complete adjudication with zero required corrections",
        "real RC remains visible",
    ),
    Path("ips-microkernel/procedures/correct.md"): (
        "only after a complete exact-head adjudication",
        "Implement only findings recorded as `required-correction`",
        "Preserve `accepted-residual` and `non-material` dispositions",
        "[adjudication](adjudicate.md) before any further correction",
    ),
    Path("ips-microkernel/procedures/merge.md"): (
        "complete focused-Issue adjudication",
        "records zero required corrections",
        "never relabel RC as Approved",
        "[adjudication](adjudicate.md)",
    ),
    Path("ips-microkernel/selectors/governance-knowledge.md"): (
        "| `adjudication` |",
        "[Review adjudication](../procedures/adjudicate.md)",
    ),
}

KNOWLEDGE_CURATION_FRAGMENTS = {
    Path("ips-microkernel/work-router.md"): (
        "Stable reusable candidates have complete disposition for every associated "
        "actionable finding and successful proof for every required correction",
        "[knowledge curation](procedures/curate-knowledge.md)",
        "complete candidate curation",
    ),
    Path("ips-microkernel/references/authority.md"): (
        "`promote-current-pr` rule",
        "without routine owner confirmation",
    ),
    Path("ips-microkernel/references/live-state.md"): (
        "| Knowledge curation | Candidate source and ordinal",
        "complete curation for every reusable candidate",
    ),
    Path("ips-microkernel/procedures/focus.md"): (
        "A complete Knowledge Curator checkpoint",
        "does not authorize material product",
        "no complete curator checkpoint selects a bounded governance follow-up",
    ),
    Path("ips-microkernel/procedures/implement.md"): (
        "Apply one completed `promote-current-pr` checkpoint",
        "selected canonical target",
    ),
    Path("ips-microkernel/procedures/publish.md"): (
        "A proved reusable candidate with complete disposition for every associated "
        "actionable finding and proof for every required correction",
        "[knowledge curation](curate-knowledge.md)",
        "after every candidate has complete curation",
    ),
    Path("ips-microkernel/procedures/adjudicate.md"): (
        "Do not classify or promote them while the Review Adjudicator role is active",
        "[knowledge curation](curate-knowledge.md)",
    ),
    Path("ips-microkernel/procedures/correct.md"): (
        "enter [knowledge curation](curate-knowledge.md) before re-review",
        "Proved correction with pending reusable candidates",
    ),
    Path("ips-microkernel/procedures/curate-knowledge.md"): (
        "distinct runtime role",
        "Freeze the candidate queue",
        "Do not review, modify implementation or guidance",
        "complete disposition for every associated actionable finding, if any",
        "A candidate with no associated actionable finding or required correction "
        "remains eligible",
        "Critical or High product impact alone never forces promotion",
        "`discarded`",
        "`already-represented`",
        "`promote-current-pr`",
        "`promote-follow-up`",
        "`deferred`",
        "`unclassified`",
        "append one curation checkpoint to the focused Issue",
        "before any promotion mutation",
        "title begins `[Knowledge candidate]`",
        "deterministic resurfacing trigger",
        "invalidates older exact-head proof and verdicts",
        "final changed head must pass required proof and independent exact-head review",
        "A post-merge candidate cannot use `promote-current-pr`",
        "ordered candidate queue",
        "For each queued candidate",
        "return to step 3 for the next queued candidate",
        "Only after the queue is exhausted",
        *REVIEW_CANDIDATE_CAPTURE_FRAGMENTS[
            Path("ips-microkernel/procedures/curate-knowledge.md")
        ],
    ),
    Path("ips-microkernel/procedures/merge.md"): (
        "every reusable candidate has complete curation",
        "Every `promote-current-pr` checkpoint must be implemented",
        "Pending, stale, or unimplemented candidate curation",
    ),
    Path("ips-microkernel/procedures/reconcile.md"): (
        "verify every pre-merge curation checkpoint",
        "route any late candidate through the Knowledge Curator",
    ),
    Path("ips-microkernel/procedures/governance-reconcile.md"): (
        "every pre-merge atomic candidate",
        "A post-merge candidate cannot use `promote-current-pr`",
        "one open `[Knowledge candidate]` Issue",
        "Governance knowledge reconciliation: no new reusable finding",
    ),
    Path("ips-microkernel/selectors/governance-knowledge.md"): (
        "Knowledge Curator",
        "normally enters the current focused PR",
        "fresh proof and independent review",
        "independently reviewed follow-up PR",
    ),
    Path("ips-microkernel/review/verdict.md"): (
        "evidence for routed knowledge curation",
        "not permission for the reviewer to classify a disposition",
    ),
}

KNOWLEDGE_CURATOR_AUTHORITY_PATH = Path("ips-microkernel/references/authority.md")
KNOWLEDGE_CURATOR_ACTION_FRAGMENTS = (
    "Freezes proved reusable candidates",
    "selects one canonical target",
    "records one disposition per atomic candidate",
)
KNOWLEDGE_CURATOR_BOUNDARY_FRAGMENTS = (
    "Is a distinct runtime role",
    "does not review, implement, move the PR head, relabel a verdict, or merge while curating",
)
KNOWLEDGE_CURATION_DISPOSITION_PATH = Path(
    "ips-microkernel/procedures/curate-knowledge.md"
)
KNOWLEDGE_CURATION_DISPOSITION_DEFINITIONS = {
    "discarded": (
        "product-specific, one-off, obvious, or not worth permanent context",
    ),
    "already-represented": ("the selected rule or guard already owns it",),
    "promote-current-pr": (
        "one bounded causal rule",
        "unmerged current focused PR",
    ),
    "promote-follow-up": ("late, cross-boundary, or too broad for the current PR",),
    "deferred": ("a named recurrence or additional-evidence trigger is required",),
    "unclassified": ("no honest canonical target or disposition is available",),
}
KNOWLEDGE_CURATION_DISPOSITION_APPLICATIONS = {
    ("discarded",): ("preserve the checkpoint as terminal recoverable evidence",),
    ("already-represented",): ("link the exact accepted rule and guard",),
    ("promote-current-pr",): (
        "one selected rule",
        "head moves, require fresh exact-head proof and independent review",
    ),
    ("promote-follow-up",): (
        "one accepted focused governance Issue",
        "independently reviewed PR",
        "without blocking the proved current merge",
    ),
    ("deferred", "unclassified"): (
        "create or reuse one open GitHub Issue",
        "title begins `[Knowledge candidate]`",
        "deterministic resurfacing trigger",
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
        "The only required owner-confirmation STOP",
        "An exact-head owner waiver is optional and owner-initiated",
        "reusable non-CI process or review knowledge",
        *REVIEW_ADJUDICATION_FRAGMENTS[Path("ips-microkernel/work-router.md")],
        *KNOWLEDGE_CURATION_FRAGMENTS[Path("ips-microkernel/work-router.md")],
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
        "The normal owner-confirmation boundary",
        "An exact-head owner waiver is a second, optional decision boundary",
        "standing policy",
        "Docker-backed proof runs in GitHub Actions",
        "A Markdown-only skip is machine-qualified",
        "A checklist criterion changes state through proof or an explicit owner acceptance",
        "A remote branch is deleted only after",
        "Public participant",
        "ADR-0019 operational recording is separate",
        "Stage A appends the current PR occurrence",
        "Stage B adds or strengthens a deduplicated machine rule",
        "CI Playbook appends a duplicate-allowed record",
        "reads selected CI Playbook leaves, and repairs test/proof scripts before `git push`",
        "not permission to silently curate unrelated governance",
        *REVIEW_ADJUDICATION_FRAGMENTS[Path("ips-microkernel/references/authority.md")],
        *KNOWLEDGE_CURATION_FRAGMENTS[Path("ips-microkernel/references/authority.md")],
    ),
    Path("ips-microkernel/references/live-state.md"): (
        "Do not enumerate every branch",
        "Do not infer current PR, Issue, check, or merge state",
        "Deterministic recovery",
        *REVIEW_ADJUDICATION_FRAGMENTS[
            Path("ips-microkernel/references/live-state.md")
        ],
        *KNOWLEDGE_CURATION_FRAGMENTS[Path("ips-microkernel/references/live-state.md")],
    ),
    Path("ips-microkernel/references/evidence.md"): (
        "Completion evidence",
        "umbrella gate",
        "Check a criterion only when it is fully proved or the owner explicitly accepts",
        "acceptance is a waiver rather than proof",
        "independent reviewer never edits Issue checklists",
    ),
    Path("ips-microkernel/references/local-tools.md"): (
        "Do not request elevated privileges",
        "route Docker-backed or environment-dependent proof to GitHub Actions",
    ),
    Path("ips-microkernel/procedures/focus.md"): (
        *KNOWLEDGE_CURATION_FRAGMENTS[Path("ips-microkernel/procedures/focus.md")],
    ),
    Path("ips-microkernel/procedures/implement.md"): (
        "Build Behavior implementation from accepted design",
        "Build Proof implementation from accepted design",
        "Do not read prior Implementation Prune Stage A occurrence files",
        "publication Gate A selects relevant CI Playbook leaves before remote push",
        *KNOWLEDGE_CURATION_FRAGMENTS[Path("ips-microkernel/procedures/implement.md")],
    ),
    Path("ips-microkernel/procedures/publish.md"): (
        "machine-qualified Markdown-only CI exception",
        "complete publication Gate A",
        "before remote push",
        "Complete publication Gate B",
        "expected full base SHA",
        "expected full head SHA",
        "remote branch tip and live PR head",
        "Editing only live PR metadata preserves successful exact-head CI",
        "Stage B finds a repository-file problem",
        "Push the one exact checked correction head",
        "Immediately read the remote branch and live PR head back",
        "before waiting for CI",
        "Require GitHub Actions to succeed for the exact read-back head",
        "without requiring a push or CI run solely to certify the rule",
        *REVIEW_ADJUDICATION_FRAGMENTS[Path("ips-microkernel/procedures/publish.md")],
        *KNOWLEDGE_CURATION_FRAGMENTS[Path("ips-microkernel/procedures/publish.md")],
    ),
    Path("ips-microkernel/procedures/adjudicate.md"): (
        *REVIEW_ADJUDICATION_FRAGMENTS[
            Path("ips-microkernel/procedures/adjudicate.md")
        ],
        *KNOWLEDGE_CURATION_FRAGMENTS[Path("ips-microkernel/procedures/adjudicate.md")],
    ),
    Path("ips-microkernel/procedures/curate-knowledge.md"): (
        "Do not enter this general curation role for Implementation Prune Stage A occurrences",
        "ADR-0019 writes those after concrete corrections",
        "Do not route CI Playbook correction records here merely because they recur",
        *KNOWLEDGE_CURATION_FRAGMENTS[
            Path("ips-microkernel/procedures/curate-knowledge.md")
        ],
    ),
    Path("ips-microkernel/procedures/correct.md"): (
        "Complete the concrete correction before any operational write-back",
        "append the current PR occurrence",
        "If no rule qualifies, write nothing",
        "Gate A reads selected CI Playbook leaves",
        "rerun Stage B without requiring a push or CI run solely to certify the rule",
        *REVIEW_ADJUDICATION_FRAGMENTS[Path("ips-microkernel/procedures/correct.md")],
        *KNOWLEDGE_CURATION_FRAGMENTS[Path("ips-microkernel/procedures/correct.md")],
    ),
    Path("ips-microkernel/procedures/merge.md"): (
        "durable owner waiver",
        "Never infer or manufacture a disposition or waiver",
        "without a separate confirmation pause",
        "defer the merge mutation",
        *REVIEW_ADJUDICATION_FRAGMENTS[Path("ips-microkernel/procedures/merge.md")],
        *KNOWLEDGE_CURATION_FRAGMENTS[Path("ips-microkernel/procedures/merge.md")],
    ),
    Path("ips-microkernel/procedures/reconcile.md"): (
        "Delete the remote branch only when",
        "Otherwise retain it",
        "leaves affected criteria unchecked",
        "governance knowledge reconciliation",
        *KNOWLEDGE_CURATION_FRAGMENTS[Path("ips-microkernel/procedures/reconcile.md")],
    ),
    Path("ips-microkernel/procedures/governance-reconcile.md"): (
        "after every focused PR merge",
        "Governance knowledge reconciliation: no new reusable finding",
        "do not create a recursive empty Issue",
        "CI runner or Actions signals",
        *KNOWLEDGE_CURATION_FRAGMENTS[
            Path("ips-microkernel/procedures/governance-reconcile.md")
        ],
    ),
    Path("ips-microkernel/selectors/governance-knowledge.md"): (
        "not an append-only incident ledger",
        "Select one canonical target",
        "accepted focused governance Issue",
        "independently reviewed follow-up PR",
        "current focused PR",
        "Rows are ordered precedence",
        "split it into atomic candidates",
        "never assign one candidate to two targets",
        "Implementation Prune Stage A occurrences",
        "bypass this selector",
        "not permanent-governance promotion candidates merely because they recur",
        *REVIEW_ADJUDICATION_FRAGMENTS[
            Path("ips-microkernel/selectors/governance-knowledge.md")
        ],
        *KNOWLEDGE_CURATION_FRAGMENTS[
            Path("ips-microkernel/selectors/governance-knowledge.md")
        ],
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
        *KNOWLEDGE_CURATION_FRAGMENTS[Path("ips-microkernel/review/verdict.md")],
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
        "fallible duplicate-preserving correction notebook",
        "before remote push",
        "no Stage A/B or proved/unproved classification",
        "Do not preload every procedure",
        "Select the first matching state",
    ),
    Path("ips-microkernel/ci/procedures/preflight.md"): (
        "after the first complete Behavior and Proof implementation",
        "CI Playbook selector",
        "repair applicable test/proof scripts before remote push",
        "Do not read prior Stage A occurrence files or the Stage B checklist",
        "Never defer CI Playbook reading",
        "Whenever local `HEAD` changes",
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
        "checks correction-record completeness",
        "does not prove, deduplicate, promote, or curate CI Playbook entries",
        "CI correction reconciliation: complete",
        "Duplicate entries are valid",
    ),
    Path("ips-microkernel/ci/procedures/failure-triage.md"): (
        "Do not preload CI Playbook history before the concrete correction",
        "After the correction exists",
        "Append Origin, Trigger, Mistake, and Correction without scanning",
        "Duplicate records are allowed",
        "Do not update Stage B for a CI failure",
        "before one ordinary remote push",
    ),
    Path("ips-microkernel/knowledge/behavior.md"): (
        "Read this checklist only after exact-head GitHub Actions succeeds",
        "immediately before initial review or re-review dispatch",
        "Each rule contains exactly Trigger, HEAD effect, Problem, Detect, Pass, Repair, and Origins",
        "Authenticate before request validation",
        "Publish exact review endpoints",
        "Invalidate head-bound review evidence",
        "Authorize a target before idempotency classification",
        "Enforce closed request contracts at runtime",
        "Serialize only reachable discriminated states",
        "Enforce constrained request parameters at runtime",
        "automatically meets the Stage B recording requirement",
        "concrete Repair text",
        "Never publish a `Stage B record: none` placeholder",
        "without requiring a push or CI run solely to prove that rule",
    ),
    Path("ips-microkernel/knowledge/correction-ledger.md"): (
        "Do not enumerate or read earlier PR record files",
        "PR, Mistake, Correction",
        "Preserve repeated Mistake and Correction text as separate occurrences",
        "Do not add `Evidence`, `Proof`, `Status`",
        "Write the occurrence immediately after the correction exists",
        "Never create a knowledge-only push or CI run to prove a Stage A occurrence",
    ),
    Path("ips-microkernel/ci/knowledge/selector.md"): (
        "Read this selector in publication Gate A",
        "before remote push",
        "Do not read the CI Playbook after remote push",
        "Duplicate entries, including identical Mistake and Correction text, are allowed",
        "Do not scan, compare, reuse, strengthen, merge, or deduplicate earlier entries",
        "Do not add Evidence, Proof, Status, proved/unproved, promotion, or permanence fields",
    ),
    Path("ips-microkernel/ci/knowledge/identity.md"): (
        "Replace legacy ownership expectations",
        "Derive exact validated token identity",
        "Cross ownership hiding with replay classification",
        "run 30627309389",
        "run 30627826543",
    ),
    Path("ips-microkernel/ci/knowledge/isolation.md"): (
        "Preserve production failure precedence",
        "same first failure as production",
    ),
    Path("ips-microkernel/ci/knowledge/contracts.md"): (
        "Reject extras through the runtime boundary",
        "Cover reachable and unreachable union states",
        "Match parameter constraints at the production boundary",
    ),
    Path("ips-microkernel/ci/knowledge/framework-runtime.md"): (
        "Cross production bundle boundaries",
        "run 30628514591",
    ),
    Path(
        "ips-microkernel/adr/0019-separate-correction-records-from-pre-review-checks.md"
    ): (
        "Keep the names distinct",
        "Make Implementation Prune Stage A an occurrence ledger",
        "Keep Implementation Prune Stage B as a post-CI pre-review check",
        "Stage B problem whose repair is HEAD-neutral",
        "Make the CI Playbook a pre-push correction notebook",
        "Do not scan existing entries for reuse or deduplication",
        "Split CI Playbook entries into proved and unproved stores",
        "Read the CI Playbook after push but before CI starts",
        "Separate operational recording from candidate proof",
    ),
    Path(
        "ips-microkernel/adr/0018-bound-post-correction-careless-mistake-writeback.md"
    ): (
        "Add one narrow exception to ADR-0017",
        "After directly correcting a real independent-review finding or exact-head CI failure",
        "the lesson is non-material and has one canonical home",
        "Knowledge write-back: none",
        "There is no pending intake queue",
        "Keep general curation separate",
        "Gate A restarts on the new local HEAD",
        "remote/PR head read-back",
        "ADR-0017 remains authoritative",
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
    Path("ips-microkernel/adr/0014-adopt-revisitable-state-governance.md"): (
        "Treat repository states as revisitable",
        "Make recurrence prevention opt-in",
        "Do not ban destructive or breaking change by category",
        "Allow an exact owner-waiver path",
        "Treat selective CI as proof disclosure",
        "skipped without evidence",
    ),
    Path("ips-microkernel/adr/0015-hide-the-human-origin-narrative.md"): (
        "Amends: ADR-0013 human-only narrative topology",
        "has no repository navigation entry and is not a README",
        "does not establish a filename-specific inbound-link checker",
        "Japanese prose uses structural Markdown line breaks only",
        "does not change or settle whether a human-only narrative participates",
    ),
    Path("ips-microkernel/adr/0016-adjudicate-review-findings-before-correction.md"): (
        "Add a Review Adjudicator runtime role",
        "Make actual Critical or High design breakage mandatory",
        "Apply three human-scale lenses below the mandatory threshold",
        "Human discoverability and bounded recoverability",
        "External technical explanation cost",
        "Material product-quality effect",
        "Record disposition before mutation",
        "Route by disposition",
        "Owner waiver remains the strong exception",
        "original RC remains RC",
    ),
    Path("ips-microkernel/adr/0017-delegate-evidence-bound-knowledge-curation.md"): (
        "Add a Knowledge Curator runtime actor",
        "Require evidence-bound curation",
        "Record one explicit disposition",
        "Prefer promotion in the current PR",
        "Keep late reconciliation",
        "Guard the delegated route",
        "`discarded`",
        "`already-represented`",
        "`promote-current-pr`",
        "`promote-follow-up`",
        "`deferred`",
        "`unclassified`",
        "without routine owner selection",
        "Final independent review and exact-head proof remain mandatory",
        "[Knowledge candidate]",
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
        "An independent verdict contains actionable findings and no exact "
        "owner waiver accepts them",
    ),
    Path("ips-microkernel/procedures/publish.md"): (
        "Actionable verdict: open [correct](correct.md).",
    ),
    Path("ips-microkernel/procedures/correct.md"): (
        "Read this file when an independent exact-head verdict contains "
        "actionable findings.",
        "Judge each finding against accepted design, focused scope, and "
        "concrete evidence.",
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
    target = MARKDOWN_BACKSLASH_ESCAPE.sub(r"\1", unescape(target))
    if target.casefold().startswith(IGNORED_PREFIXES):
        return None
    return unquote(urlsplit(target).path)


def _normalize_reference_label(label: str) -> str:
    label = re.sub(r"(?m)^[ \t]*(?:>[ \t]?)+", "", label)
    return " ".join(label.split()).casefold()


def markdown_link_targets(content: str) -> list[str]:
    targets = [match.group(1) for match in MARKDOWN_LINK.finditer(content)]
    targets.extend(
        next(group for group in match.groups() if group is not None)
        for match in MARKDOWN_HTML_ANCHOR.finditer(content)
    )
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

    human_context_documents = {
        path
        for path in ips_root.glob("*.md")
        if IPS_HUMAN_CONTEXT_MARKER in path.read_text(encoding="utf-8")
        and not IPS_RUNTIME_MARKER.search(path.read_text(encoding="utf-8"))
    }
    actual_top_level_entries = frozenset(
        path.name
        for path in ips_root.iterdir()
        if (
            path.is_file()
            or (path.is_dir() and any(child.is_file() for child in path.rglob("*")))
        )
        and path not in human_context_documents
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
        path for path in ips_root.glob("*.md") if path not in human_context_documents
    ]
    for relative_directory in IPS_RUNTIME_DIRECTORIES:
        runtime_directory = ips_root / relative_directory
        if runtime_directory.is_dir():
            runtime_paths.extend(
                path for path in runtime_directory.rglob("*") if path.is_file()
            )
    actual_files = frozenset(path.relative_to(ips_root) for path in runtime_paths)
    stage_a_record_files = frozenset(
        path for path in actual_files if STAGE_A_RECORD_PATH.fullmatch(path.as_posix())
    )
    for unexpected_path in sorted(
        actual_files - EXPECTED_IPS_RUNTIME_FILES - stage_a_record_files
    ):
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


def _validate_stage_a_occurrence_records(failures: list[str]) -> None:
    records_root = REPOSITORY_ROOT / "ips-microkernel" / "knowledge" / "corrections"
    if not records_root.is_dir():
        failures.append("missing Stage A correction-record directory")
        return

    record_paths = sorted(records_root.glob("pr-*.md"))
    if not record_paths:
        failures.append("Stage A correction-record directory has no PR records")
        return

    occurrence_heading = re.compile(r"(?m)^### Occurrence (\d+)\s*$")
    field_heading = re.compile(r"(?m)^- \*\*(PR|Mistake|Correction):\*\*")
    for path in record_paths:
        relative_path = path.relative_to(REPOSITORY_ROOT)
        match = re.fullmatch(r"pr-(\d{4})\.md", path.name)
        if match is None:
            failures.append(
                f"{relative_path.as_posix()}: invalid Stage A record filename"
            )
            continue
        expected_pr = int(match.group(1))
        content = path.read_text(encoding="utf-8")
        if (
            content.count("<!-- ips-data: implementation-correction-occurrences -->")
            != 1
        ):
            failures.append(
                f"{relative_path.as_posix()}: expected one Stage A data marker"
            )

        headings = list(occurrence_heading.finditer(content))
        numbers = [int(item.group(1)) for item in headings]
        if numbers != list(range(1, len(numbers) + 1)) or not numbers:
            failures.append(
                f"{relative_path.as_posix()}: Stage A occurrences must be non-empty "
                "and sequential from 1"
            )
            continue

        for index, heading in enumerate(headings):
            end = (
                headings[index + 1].start()
                if index + 1 < len(headings)
                else len(content)
            )
            block = content[heading.end() : end]
            fields = field_heading.findall(block)
            if fields != ["PR", "Mistake", "Correction"]:
                failures.append(
                    f"{relative_path.as_posix()}: occurrence {numbers[index]} must "
                    "contain exactly PR, Mistake, Correction in order"
                )
            pr_field = re.search(r"(?m)^- \*\*PR:\*\* PR #(\d+)\s*$", block)
            if pr_field is None or int(pr_field.group(1)) != expected_pr:
                failures.append(
                    f"{relative_path.as_posix()}: occurrence {numbers[index]} PR "
                    "must match its record filename"
                )


def _validate_stage_b_rules(failures: list[str]) -> None:
    relative_path = Path("ips-microkernel/knowledge/behavior.md")
    path = REPOSITORY_ROOT / relative_path
    if not path.is_file():
        return
    content = path.read_text(encoding="utf-8")
    if "## Rules" not in content or "## Execution and correction" not in content:
        failures.append(f"{relative_path.as_posix()}: missing Stage B rule section")
        return
    rules = content.split("## Rules", maxsplit=1)[1].split(
        "## Execution and correction", maxsplit=1
    )[0]
    heading_pattern = re.compile(r"(?m)^### (.+?)\s*$")
    field_pattern = re.compile(
        r"(?m)^- \*\*(Trigger|HEAD effect|Problem|Detect|Pass|Repair|Origins):\*\*"
    )
    headings = list(heading_pattern.finditer(rules))
    titles = [heading.group(1) for heading in headings]
    duplicates = sorted(title for title, count in Counter(titles).items() if count > 1)
    if duplicates:
        failures.append(
            f"{relative_path.as_posix()}: duplicate Stage B rule titles {duplicates!r}"
        )
    if not headings:
        failures.append(f"{relative_path.as_posix()}: Stage B has no rules")
        return
    expected_fields = [
        "Trigger",
        "HEAD effect",
        "Problem",
        "Detect",
        "Pass",
        "Repair",
        "Origins",
    ]
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(rules)
        block = rules[heading.end() : end]
        fields = field_pattern.findall(block)
        if fields != expected_fields:
            failures.append(
                f"{relative_path.as_posix()}: Stage B rule {heading.group(1)!r} "
                "must contain exactly Trigger, HEAD effect, Problem, Detect, "
                "Pass, Repair, Origins in order"
            )
        if not re.search(r"(?m)^- \*\*HEAD effect:\*\* `(neutral|moving)`\s*$", block):
            failures.append(
                f"{relative_path.as_posix()}: Stage B rule {heading.group(1)!r} "
                "must declare HEAD effect as neutral or moving"
            )


def _validate_ci_playbook_records(failures: list[str]) -> None:
    knowledge_root = REPOSITORY_ROOT / "ips-microkernel" / "ci" / "knowledge"
    heading_pattern = re.compile(r"(?m)^### (.+?)\s*$")
    field_pattern = re.compile(r"(?m)^- \*\*(Origin|Trigger|Mistake|Correction):\*\*")
    expected_fields = ["Origin", "Trigger", "Mistake", "Correction"]
    for path in sorted(knowledge_root.glob("*.md")):
        if path.name == "selector.md":
            continue
        relative_path = path.relative_to(REPOSITORY_ROOT)
        content = path.read_text(encoding="utf-8")
        normalized = " ".join(content.split())
        if "Before remote push" not in normalized:
            failures.append(
                f"{relative_path.as_posix()}: CI Playbook leaf must be read before remote push"
            )
        if "## Correction records" not in content or "## Return" not in content:
            failures.append(
                f"{relative_path.as_posix()}: missing CI Playbook correction section"
            )
            continue
        records = content.split("## Correction records", maxsplit=1)[1].split(
            "## Return", maxsplit=1
        )[0]
        headings = list(heading_pattern.finditer(records))
        if not headings:
            failures.append(
                f"{relative_path.as_posix()}: CI Playbook leaf has no correction records"
            )
            continue
        for index, heading in enumerate(headings):
            end = (
                headings[index + 1].start()
                if index + 1 < len(headings)
                else len(records)
            )
            block = records[heading.end() : end]
            fields = field_pattern.findall(block)
            if fields != expected_fields:
                failures.append(
                    f"{relative_path.as_posix()}: CI Playbook record "
                    f"{heading.group(1)!r} must contain exactly Origin, Trigger, "
                    "Mistake, Correction in order"
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
                    "standing owner-confirmation gates are reserved for "
                    "focused-slice selection"
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


def _validate_knowledge_curator_actor_boundary(failures: list[str]) -> None:
    relative_path = KNOWLEDGE_CURATOR_AUTHORITY_PATH
    path = REPOSITORY_ROOT / relative_path
    if not path.is_file():
        return

    actor_rows: list[tuple[int, list[str]]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells and cells[0] == "Knowledge Curator":
            actor_rows.append((line_number, cells))

    if len(actor_rows) != 1:
        failures.append(
            f"{relative_path.as_posix()}: Knowledge Curator actor row expected "
            f"exactly once, found {len(actor_rows)}"
        )
        return

    line_number, cells = actor_rows[0]
    if len(cells) != 3:
        failures.append(
            f"{relative_path.as_posix()}:{line_number}: malformed Knowledge "
            "Curator actor row"
        )
        return

    actions = " ".join(cells[1].split())
    boundary = " ".join(cells[2].split())
    for fragment in KNOWLEDGE_CURATOR_ACTION_FRAGMENTS:
        if fragment not in actions:
            failures.append(
                f"{relative_path.as_posix()}:{line_number}: Knowledge Curator "
                f"actor row missing action {fragment!r}"
            )
    for fragment in KNOWLEDGE_CURATOR_BOUNDARY_FRAGMENTS:
        if fragment not in boundary:
            failures.append(
                f"{relative_path.as_posix()}:{line_number}: Knowledge Curator "
                f"actor row missing boundary {fragment!r}"
            )


def _knowledge_curation_candidate_is_eligible(
    *,
    stable_evidence: bool,
    associated_finding_disposition_complete: bool | None,
    required_correction_proof_complete: bool | None,
) -> bool:
    return (
        stable_evidence
        and associated_finding_disposition_complete is not False
        and required_correction_proof_complete is not False
    )


def _named_disposition_bullets(
    content: str,
    *,
    start_marker: str,
    end_marker: str,
) -> list[tuple[tuple[str, ...], str, int]]:
    start_index = content.index(start_marker)
    end_index = content.index(end_marker, start_index)
    line_offset = content[:start_index].count("\n")
    entries: list[tuple[tuple[str, ...], str, int]] = []
    current_names: tuple[str, ...] | None = None
    current_parts: list[str] = []
    current_line = 0

    for relative_line, line in enumerate(
        content[start_index:end_index].splitlines(), start=1
    ):
        match = re.match(
            r"^\s+- `([^`]+)`(?:(?: or )`([^`]+)`)?\: (.*)$",
            line,
        )
        if match:
            if current_names is not None:
                entries.append(
                    (
                        current_names,
                        " ".join(" ".join(current_parts).split()),
                        current_line,
                    )
                )
            current_names = tuple(
                name for name in (match.group(1), match.group(2)) if name
            )
            current_parts = [match.group(3)]
            current_line = line_offset + relative_line
        elif current_names is not None and line.strip():
            current_parts.append(line.strip())

    if current_names is not None:
        entries.append(
            (
                current_names,
                " ".join(" ".join(current_parts).split()),
                current_line,
            )
        )

    return entries


def _validate_knowledge_curation_disposition_semantics(
    failures: list[str],
) -> None:
    relative_path = KNOWLEDGE_CURATION_DISPOSITION_PATH
    path = REPOSITORY_ROOT / relative_path
    if not path.is_file():
        return

    content = path.read_text(encoding="utf-8")
    try:
        definition_entries = _named_disposition_bullets(
            content,
            start_marker="7. Assign exactly one disposition:",
            end_marker="8. Before implementation",
        )
        application_entries = _named_disposition_bullets(
            content,
            start_marker="9. Apply the disposition:",
            end_marker="10. After one outcome",
        )
    except ValueError:
        failures.append(
            f"{relative_path.as_posix()}: missing structured disposition section"
        )
        return

    expected_definition_names = {
        (name,) for name in KNOWLEDGE_CURATION_DISPOSITION_DEFINITIONS
    }
    actual_definition_names = [names for names, _text, _line in definition_entries]
    if set(actual_definition_names) != expected_definition_names or len(
        actual_definition_names
    ) != len(expected_definition_names):
        failures.append(
            f"{relative_path.as_posix()}: disposition definitions must contain "
            "each canonical label exactly once"
        )

    definition_by_name = {
        names[0]: (text, line_number)
        for names, text, line_number in definition_entries
        if len(names) == 1
    }
    for name, required_fragments in KNOWLEDGE_CURATION_DISPOSITION_DEFINITIONS.items():
        entry = definition_by_name.get(name)
        if entry is None:
            continue
        text, line_number = entry
        for fragment in required_fragments:
            if fragment not in text:
                failures.append(
                    f"{relative_path.as_posix()}:{line_number}: {name!r} "
                    f"disposition definition missing semantic {fragment!r}"
                )

    expected_application_names = set(KNOWLEDGE_CURATION_DISPOSITION_APPLICATIONS)
    actual_application_names = [names for names, _text, _line in application_entries]
    if set(actual_application_names) != expected_application_names or len(
        actual_application_names
    ) != len(expected_application_names):
        failures.append(
            f"{relative_path.as_posix()}: disposition applications must contain "
            "each canonical route exactly once"
        )

    application_by_names = {
        names: (text, line_number) for names, text, line_number in application_entries
    }
    for (
        names,
        required_fragments,
    ) in KNOWLEDGE_CURATION_DISPOSITION_APPLICATIONS.items():
        entry = application_by_names.get(names)
        if entry is None:
            continue
        text, line_number = entry
        for fragment in required_fragments:
            if fragment not in text:
                rendered_names = " or ".join(repr(name) for name in names)
                failures.append(
                    f"{relative_path.as_posix()}:{line_number}: "
                    f"{rendered_names} disposition application missing semantic "
                    f"{fragment!r}"
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


def _validate_required_governance_text(
    failures: list[str],
    required_text: dict[Path, tuple[str, ...]],
) -> None:
    for relative_path, required_fragments in required_text.items():
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


def governance_failures() -> list[str]:
    failures: list[str] = []

    _validate_legacy_governance_layout(failures)

    for relative_path in REQUIRED_GOVERNANCE_FILES:
        if not (REPOSITORY_ROOT / relative_path).is_file():
            failures.append(
                f"missing required governance file {relative_path.as_posix()}"
            )

    _validate_required_governance_text(failures, REQUIRED_GOVERNANCE_TEXT)

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
    _validate_stage_a_occurrence_records(failures)
    _validate_stage_b_rules(failures)
    _validate_ci_playbook_records(failures)
    _validate_owner_confirmation_boundary(failures, governance_paths)
    _validate_knowledge_curator_actor_boundary(failures)
    _validate_knowledge_curation_disposition_semantics(failures)
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
