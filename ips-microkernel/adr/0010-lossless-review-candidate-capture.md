# ADR-0010: Preserve every reusable review candidate in one verdict

- Status: Accepted
- Date: 2026-07-26
- Deciders: ReactorFront
- Related: ADR-0009, Issue #36

## Context

ADR-0009 established a reviewed write path for reusable governance knowledge.
It preserved the independent reviewer's one-comment boundary, added one
`Reusable governance candidate` section to the verdict, and made post-merge
reconciliation process an ordered candidate queue.

The downstream queue can process several candidates, but the review inspection
procedure still asked for one reusable candidate. A single review cycle can
discover several independent reusable signals. Reporting only one would lose
the others before they reach the queue, even though every later state is
multi-candidate safe.

Adding comments or headings would weaken the review mutation boundary. Treating
one compound observation as several destinations would weaken atomic routing.

## Decision

### Keep one publication boundary

The reviewer still publishes exactly one top-level verdict comment and exactly
one `Reusable governance candidate` section. Exhaustive capture does not grant
permission to edit implementation, guidance, Issues, or PR metadata.

### Serialize every atomic candidate

Inspection classifies every evidenced reusable process or review candidate
discovered in that review cycle. It splits compound observations into atomic
root-cause candidates and preserves their stable discovery order.

The verdict section contains exactly one of:

- `none`, only when no reusable candidate was discovered
- a numbered list with one item for every atomic candidate

Each numbered item records one signal and its exact evidence. One item never
combines several root causes or selects several canonical targets.

### Expand the complete verdict

Post-merge governance reconciliation expands every numbered candidate item from
every verdict into the ordered candidate queue. It then adds distinct reusable
signals proved by corrections, recovery, evidence reconciliation, or cleanup
and deduplicates only identical stable evidence.

The existing queue, one-target selector, per-candidate outcome, focused-Issue
promotion, independently reviewed update, and queue-exhaustion aggregate remain
unchanged.

### Guard capture and ingestion

Documentation verification rejects:

- singular-only review capture
- a missing atomic-list contract
- permission to record `none` when a candidate exists
- more than one candidate section
- loss of later verdict items during queue ingestion

Focused negative regressions mutate each boundary independently so topology
checks alone cannot prove lossless capture.

## Consequences

### Positive

- Every reusable review signal can cross the one-comment boundary.
- The reviewer mutation surface does not grow.
- Atomic candidates enter the already-proved multi-candidate queue directly.
- A false `none` or first-item-only regression fails documentation verification.

### Costs

- Reviewers must split and order independent reusable signals before
  publication.
- Verdict comments may contain a short numbered list instead of one sentence.
- Candidate completeness still requires reviewer judgment bounded by exact
  evidence and independent review.

## Rejected alternatives

- Permit one verdict comment per reusable candidate.
- Permit several `Reusable governance candidate` headings.
- Keep only the most important candidate.
- Put several root causes in one list item.
- Infer omitted reviewer candidates after merge without stable evidence.
