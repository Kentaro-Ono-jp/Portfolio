# ADR-0018: Bound post-correction careless-mistake write-back

- Status: Accepted
- Date: 2026-08-01
- Deciders: ReactorFront
- Amends: ADR-0017 direct-implementer promotion boundary
- Related: ADR-0008, ADR-0009, ADR-0014, Issue #58, PR #57

## Context

ADR-0017 separates reusable-governance judgment from implementation. Its
Knowledge Curator freezes proved candidates, selects a canonical target, and
records a disposition before an implementation actor mutates guidance. It
rejects general direct implementer promotion because combining evidence,
judgment, and mutation would allow speculative or material rules to accumulate.

PR #57 exposed a narrower problem. After a real review or CI correction, a
small recurring mistake can already have stable evidence, an obvious phase,
one cheap check, and one canonical Behavior or Proof home. Sending every such
lesson through the general six-disposition curator route adds process larger
than the careless mistake and creates another opportunity to omit the lesson
before the next push.

The repository needs a low-discretion correction write-back without turning
implementation into general knowledge curation or reading past failures as a
first-pass design template.

## Decision

### Add one narrow exception to ADR-0017

After directly correcting a real independent-review finding or exact-head CI
failure, the implementation actor must make one explicit careless-mistake
write-back decision before the next task-branch push. This exception applies
only when every admission guard is true:

- stable evidence is the real review comment or CI run that required the
  correction;
- recurrence is plausible;
- the pre-dispatch check has one clear actionable answer;
- the check is cheap compared with another review or CI cycle;
- the lesson changes future Behavior or Proof implementation;
- the lesson is non-material and has one canonical home.

The actor strengthens one existing atomic entry when possible. Otherwise it
adds one Behavior entry with phase `pre-CI` or `pre-review`, or one Proof entry
to the matching CI leaf. A compound lesson is split between those homes. An
admitted Proof lesson without a home adds one bounded leaf and selector route.

When no lesson satisfies every guard, the PR correction evidence records
`Knowledge write-back: none` and a concrete rationale. There is no pending
intake queue.

### Keep general curation separate

This direct route is not a replacement for the Knowledge Curator. Material
product, delivery, architecture, security, actor-authority, or collaboration-
workflow decisions; speculative advice; one-off bugs; and candidates requiring
context-cost or disposition judgment remain under focus and ADR governance or
ADR-0017 curation.

The independent reviewer still only supplies evidence and a verdict. The
Review Adjudicator still disposes actionable findings before correction. The
implementation actor first corrects only the adjudicated or CI-proved cause,
then writes the admitted low-discretion lesson. It never uses the exception to
reclassify a finding or promote unrelated governance.

### Bind write-back to the same lifecycle gates

Behavior and Proof implementation begin from accepted design without loading
the mistake guides. After the first complete implementation, Gate A selects
only triggered `pre-CI` Behavior entries and CI leaves against the complete
committed delta.

After a correction and any direct write-back, the complete repository change
is verified, committed, and Gate A restarts on the new local HEAD. Push is
followed immediately by remote/PR head read-back and stale-evidence
invalidation, then exact-head CI. Gate B selects `pre-review` Behavior entries
only after that CI succeeds. A PR metadata-only repair is head-neutral; a
repository-file repair returns through Gate A and new CI.

Documentation verification owns the admission guards, direct homes, explicit
none outcome, absence of an intake queue, Gate A restart, push read-back, Gate
B dispatch boundary, and the continuing ADR-0017 general-curation boundary.

## Consequences

### Positive

- Cheap, evidenced correction lessons become available before the next push or
  reviewer dispatch.
- The write route cannot silently omit a decision or leave an unowned pending
  candidate.
- General candidate judgment and material authority changes remain separated
  from implementation.
- Every tracked write-back receives exact-head CI and independent review with
  the correction that caused it.

### Costs

- The implementation actor must classify every review or CI correction before
  push.
- Adding or strengthening an entry moves HEAD and restarts Gate A.
- The repository must maintain focused mutation tests for the narrow exception.

## Rejected alternatives

### Route every careless mistake through the Knowledge Curator

Rejected for this narrow class because the stable source, admission decision,
canonical destination, and timing are deliberately bounded; the general role
would cost more than the prevented cycle. ADR-0017 remains authoritative for
all candidates outside these guards.

### Read mistake guides before first-pass implementation

Rejected because past failure shapes could bias Behavior or Proof away from
the accepted design.

### Keep a pending intake ledger

Rejected because it permits omission and creates a second backlog. The lesson
is written directly or the correction evidence records an explicit none.
