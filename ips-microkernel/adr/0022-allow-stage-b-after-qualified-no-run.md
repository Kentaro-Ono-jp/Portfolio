# ADR-0022: Allow Stage B after a qualified no-run candidate

- Status: Accepted
- Date: 2026-08-02
- Deciders: ReactorFront
- Supersedes: ADR-0019
- Related: ADR-0014, ADR-0017, ADR-0021, Issue #73, PR #74

## Context

ADR-0019 separated implementation-correction occurrences, pre-review Stage B
checks, and pre-push CI Playbook records. It correctly made exact-head Actions
or the machine-qualified exception the candidate-proof boundary, but defined
Publication Gate B and Stage B themselves as reachable only after successful
exact-head Actions.

The repository's governed Markdown-only exception intentionally produces no
workflow when every changed path is non-executable Markdown, the exact base and
successful base runtime proof are recorded, local documentation and diff proof
pass, the review-head commit carries a supported skip instruction, and an
independent reviewer inspects that same head. The absent workflow is a
qualified limitation, never passing evidence.

A Stage B rule now verifies exact review endpoints, the complete Markdown path
inventory, and selected, executed, carried, and skipped group and test-file
counts. Excluding a qualified no-run head from Stage B would make that rule
unreachable in the case it is designed to guard. Treating the missing workflow
as successful CI would instead falsify the evidence model.

## Decision

### Preserve ADR-0019's separation

Keep the following ADR-0019 decisions:

- Stage A is an append-only per-PR implementation-correction occurrence
  ledger with no proof or permanence claim.
- Stage B is a small deduplicated set of mechanically decidable pre-review
  checks with explicit trigger, HEAD effect, problem, detection, pass, repair,
  and origins fields.
- The CI Playbook remains a selector-routed pre-push correction notebook.
- Operational recording does not prove an occurrence, rule, or note, and
  candidate proof does not make operational text permanently true.

ADR-0022 changes only the Stage B entry and re-entry authority described below.

### Give Publication Gate B two exact inputs

Publication Gate B may begin only after one of these exact-head states:

1. successful exact-head GitHub Actions; or
2. the complete governed machine-qualified no-run exception.

Normal exact-head Actions remains the default. Uncertainty or any failed
exception condition restores normal Actions proof. A missing workflow is
recorded only as a qualified limitation and never as passing evidence.

### Execute Stage B against the applicable evidence source

Immediately before initial review or re-review dispatch, execute Stage B
against the live PR base and head.

- For normal proof, use the successful exact-head Actions plan and inventory.
- For a qualified no-run head, confirm that no exact-head run exists and use
  the exact committed-tree Gate A planner, required local documentation and
  diff proof, complete live base-to-head path inventory, and live PR metadata.

The PR description and copyable review prompt must agree with that applicable
source. Stage B never manufactures a successful workflow conclusion for the
exception branch.

### Re-enter through proof or the complete exception after a moving repair

When a Stage B repair moves `HEAD`, correct the repository, append Stage A when
the change corrects an implementation mistake, complete pre-push CI Playbook
hardening, make one ordinary push, and obtain either successful new exact-head
Actions or the complete machine-qualified no-run exception before executing
Stage B again.

When a repair is HEAD-neutral, correct and read back the live surface, then
rerun the applicable Stage B rule without creating a proof-only push. If
persisting that rule later moves `HEAD`, the complete repository candidate
returns through the same Actions-or-qualified-exception boundary.

## Consequences

### Positive

- Qualified Markdown-only heads receive the same mechanical pre-review
  endpoint and inventory checks as normal Actions-backed heads.
- The exception remains explicit and cannot be mislabeled as passing CI.
- Moving repairs still invalidate stale proof and review evidence.
- Stage A, Stage B, and CI Playbook responsibilities remain separated.

### Costs

- Stage B implementations must branch on two exact evidence sources.
- Review metadata for a no-run head must carry a complete self-contained
  exception record.
- Accepted ADR-0019 becomes superseded even though most of its separation
  decisions are carried forward unchanged.

## Rejected alternatives

### Skip Stage B for qualified no-run heads

Rejected because Markdown-only exception metadata contains exact endpoint,
path, and verification claims that benefit directly from mechanical Stage B
inspection.

### Treat an absent workflow as a successful Stage B prerequisite

Rejected because absence is a limitation and cannot supply passing evidence.

### Amend ADR-0019 in place

Rejected because accepted decisions are historical records. A changed
decision receives a new ADR and explicit supersession.
