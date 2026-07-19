# ADR-0006: Consolidate repository-owned AI guidance

- Status: Accepted
- Date: 2026-07-19
- Supersedes: [ADR-0005](0005-repository-owned-ai-collaboration.md)
- Tracking issue: [#11](https://github.com/Kentaro-Ono-jp/Portfolio/issues/11)

## Context

ADR-0005 correctly moved durable AI collaboration rules from local memory into
reviewed repository sources. Its first implementation favored defensive
separation: eight files under `docs/ai`, plus tool-named root entrypoints.

That layout preserved the contract but repeated the same source hierarchy,
actor boundaries, exact-check rules, public-safety rules, and lifecycle steps
across overview, policy, lifecycle, evidence, and prompt documents. The
repetition increased cold-task context and made the contract harder to scan.

The public `AGENTS.md` name was also easy to confuse with separately injected
machine-local guidance. `CLAUDE.md` implied a vendor-specific relationship that
the repository does not require.

## Decision

Keep ADR-0005's repository-owned operating model, but replace its file topology:

- `GIT_AGENTS.md` is the explicit public repository entrypoint.
- `AI_GUIDANCE.md` is a minimal, vendor-neutral compatibility pointer.
- `docs/ai/README.md` is the single implementation, authority, evidence, and
  cleanup contract.
- `docs/ai/PR_REVIEW.md` is the single initial-review and re-review contract.

Each durable rule has one authoritative home. Other files link to that rule
instead of restating it. Use a table only for exact repeated-field mappings,
such as actor-to-authority boundaries; use short directives, numbered
workflows, and explicit stop conditions elsewhere.

Preserve these invariants from ADR-0005:

- accepted design, stable repository guidance, live GitHub evidence, and local
  orientation remain separate authority layers
- the repository owner remains the only source of authorization
- implementation uses focused Issues, branches, Draft PR checkpoints, exact
  checks, independent review, and merged-main evidence
- independent review remains isolated, static, comment-only, exact-head, and
  responsible for removing temporary data
- broad audits occur only after a concrete discrepancy
- Issue checkboxes remain evidence-backed post-merge delivery records
- public guidance excludes secrets, private context, local paths, raw chats,
  hidden reasoning, and unfiltered memory

The conventional Codex `AGENTS.md` auto-discovery name is intentionally not
retained. Cold tasks must be routed explicitly through the root README,
`AI_GUIDANCE.md`, the task request, or local routing memory. Repository tests
verify that every tracked route reaches `GIT_AGENTS.md` and the two-file
`docs/ai` contract.

Fast-changing project status remains in Issue #1 and the active focused
Issue, PR, commits, verdicts, and Actions runs.

## Consequences

### Positive

- A fresh agent reads fewer files and receives each rule once.
- Public and machine-local guidance no longer share the same filename.
- Review and re-review use one exact, copyable contract.
- Vendor-neutral naming avoids implying a Claude-specific project dependency.
- Documentation verification protects semantic invariants rather than an
  unnecessarily fragmented topology.

### Costs

- Codex will not auto-discover `GIT_AGENTS.md` by filename alone.
- Entry routes and local routing memory must remain aligned with the renamed
  file.
- Consolidated documents require disciplined headings so one file does not
  become an unstructured policy dump.

## Rejected alternatives

- Keep all eight files and shorten sentences without removing duplication.
- Rename only the root files while preserving the fragmented contract.
- Keep a tiny public `AGENTS.md` redirect, which would preserve the name
  collision the change is intended to remove.
- Collapse every rule and review prompt into one monolithic document.
- Remove exact mutation, review, evidence, or public-safety boundaries as
  assumed agent common sense.

## Revisit when

- external contributors require zero-prompt tool auto-discovery
- another actor or automation gains durable write authority
- the two-file contract develops material duplication
- a technical permission boundary can replace part of the operating contract
