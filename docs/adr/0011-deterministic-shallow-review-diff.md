# ADR-0011: Prove complete review diffs without a local merge base

- Status: Accepted
- Date: 2026-07-26
- Deciders: ReactorFront
- Related: ADR-0008, ADR-0009, ADR-0010, Issue #38

## Context

ADR-0008 isolated independent review in a shallow clone. ADR-0009 and
ADR-0010 then made review findings and every reusable governance candidate
durable without expanding reviewer mutation authority.

The approved review of PR #37 exposed a remaining setup ambiguity. The exact
head was cloned with `--depth 1 --no-tags`, and the exact base was fetched at
depth one, but a three-dot comparison still failed because the shallow commit
graph had no merge base. The reviewer recovered the complete diff through
GitHub PR evidence and an exact endpoint tree comparison.

Unbounded deepening would weaken isolation and make review time depend on
repository history. Falling back to the canonical implementation workspace
would violate reviewer authority. Approving from only one incomplete view
would weaken complete-diff proof.

## Decision

### Require both exact endpoints

Every review input includes the expected full base SHA and expected full head
SHA. Setup resolves the live PR endpoints and requires both to equal the
declared values before local inspection.

### Keep bounded shallow isolation

Setup shallow-clones the exact head with `--depth 1 --no-tags`, then fetches the
exact base commit object separately with a second depth-one fetch. It proves
both commit objects directly. It does not deepen, unshallow, reuse, or inspect
the canonical workspace.

### Use two independent complete-diff views

Inspection obtains:

1. the canonical GitHub PR patch and complete paginated file inventory, without
   depending on the local commit graph
2. an exact endpoint tree patch and file inventory from the isolated clone
   using `git diff <expected-base-sha> <expected-head-sha>`

The endpoint comparison is intentionally two-endpoint and does not require a
merge base. A three-dot comparison may be diagnostic when a merge base exists,
but it is never the only complete-diff proof in a shallow clone.

### Require inventory agreement

The reviewer normalizes path and change-status inventories from GitHub and the
endpoint tree comparison. Review proceeds only when both views cover the same
complete focused file set. Patch presentation differences and binary metadata
are recorded, but an unexplained file or status mismatch blocks approval and
routes through live-state recovery.

### Protect the fallback

Documentation verification requires:

- both expected endpoint inputs
- exact bounded base fetch and commit proof
- endpoint-tree commands that do not require a merge base
- canonical GitHub patch and paginated inventory evidence
- explicit inventory agreement before inspection
- the existing exact-head, isolated-workspace, one-comment, and cleanup guards

Focused negative regressions remove each boundary independently.

## Consequences

### Positive

- Complete review does not depend on a local merge base.
- Isolation remains depth-limited and independent of the canonical workspace.
- Wrong or stale base SHAs become explicit setup failures.
- GitHub and local tree evidence cross-check each other before approval.

### Costs

- Review inputs carry one additional exact SHA.
- Review setup performs one bounded base-object fetch.
- Review inspection must normalize and compare two file inventories.
- GitHub patch limitations remain reportable evidence rather than silent
  approval.

## Rejected alternatives

- Unshallow every review clone.
- Deepen repeatedly until an arbitrary merge base appears.
- Use a three-dot diff as the only complete-diff proof.
- Read the canonical implementation workspace for missing history.
- Trust PR file counts without inspecting the patch and endpoint trees.
