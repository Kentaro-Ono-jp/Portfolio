# ADR-0024: Adjudicate correction-loop convergence

- Status: Accepted
- Date: 2026-08-09
- Deciders: ReactorFront
- Supersedes: ADR-0016
- Amends: ADR-0017 required-correction evidence eligibility
- Related: ADR-0014, ADR-0017, Issue #108, PR #107, Issue #106

## Context

ADR-0016 inserted a Review Adjudicator between an exact-head
`Changes requested` verdict and correction or merge. It preserved independent
review sensitivity while allowing each finding to be recorded as
`required-correction`, `accepted-residual`, or `non-material`.

Its decision boundary remained local to one reviewed head. Any adjudication
with a required correction routed back through implementation, exact-head
proof, and independent re-review unless the repository owner supplied an exact
waiver. The next adjudication judged the new head without an explicit decision
about the correction chain as a whole.

PR #107 made that limitation concrete. Five exact-head `Changes requested`
cycles reported twelve finding instances, and the implementation accumulated
sixteen correction occurrences. The review sensitivity remained useful and
found real AWS authority defects. The lifecycle nevertheless lacked an
ordinary place to decide that further correction was no longer selected after
considering the accumulated quality, complexity, quota pressure, flexibility,
and present acceptance. Its final named residual used owner waiver to stop.

Requiring advance proof of an optimal stopping rule would reproduce the same
completeness seeking at the governance layer. The repository instead needs a
small, truthful, revisitable experiment whose effectiveness can be judged only
through later ordinary operation.

## Decision

### Preserve one Review Adjudicator role and independent review

Carry forward ADR-0016's existing Review Adjudicator. Do not add a convergence
actor or another runtime role.

The independent reviewer remains isolated, evidence-maximizing, free to report
every newly evidenced finding, and limited to its one honest verdict comment.
The Review Adjudicator freezes the exact reviewed head, does not implement or
merge while adjudicating, and never relabels `Changes requested` as Approved.

Continue to record every current finding as exactly one of
`required-correction`, `accepted-residual`, or `non-material`. Reviewer
severity remains evidence rather than outcome authority.

### Judge the applicable correction chain

In addition to the current exact head and verdict, freeze the applicable
ordered chain of earlier reviewed heads, real verdict URLs, adjudication
checkpoints, correction heads, and declared deltas. An initial review has a
one-verdict chain; missing history is never invented.

After disposing every current finding, record exactly one aggregate decision:

- `continue-correction`: select the current required corrections for another
  ordinary correction and re-review cycle;
- `converge`: accept the current exact head for merge routing with every
  unresolved finding and known regression risk still visible.

### Allow convergence without a quality veto

`converge` may retain one or more findings labelled `required-correction`. It
may be chosen when another correction could improve quality, the candidate may
regress relative to an earlier state, reviewer severity is Critical or High,
no future correction is selected, or the stopping point cannot be proved
optimal.

The adjudicator considers accepted scope and design, finding materiality,
marginal quality gain, added complexity, regression exposure, explanation
cost, quota pressure, future flexibility, and present acceptance holistically.
None is a mandatory veto, numeric score, vote, cycle cap, or mechanical
threshold.

This authority does not manufacture missing identity or evidence. Exact-head
and live-state checks, current proof or its governed limitation, candidate
curation, and merge checks retain their own ordinary boundaries.

### Record one truthful chain decision

Before correction or merge, append one focused-Issue checkpoint containing:

- exact reviewed head and stable real-verdict URL;
- the applicable ordered review, adjudication, and correction-chain summary;
- every current finding, evidence, and individual disposition;
- unresolved required corrections, accepted residuals, and known regression
  risk;
- exactly one `continue-correction` or `converge` decision; and
- a concise reason why another correction is or is not selected.

The checkpoint expires when the PR head or recorded chain identity changes.
The real RC remains RC.

### Route convergence separately from owner waiver

An Approved verdict still bypasses adjudication. A `continue-correction`
checkpoint routes to correction. A `converge` checkpoint routes through any
required candidate curation and then to merge, including when named required
corrections remain.

Owner waiver remains a separate stronger owner decision when the adjudicator
selected `continue-correction` but the owner explicitly accepts the exact head.
It is not required for ordinary adjudicator convergence.

An accepted residual completes the current lifecycle. It creates no follow-up
Issue, backlog item, deadline, assigned action, or promise of later correction.
Later material evidence is judged from its own future focused scope.

Reusable governance candidates remain separate evidence for the Knowledge
Curator. Convergence does not classify or silently promote them. ADR-0017's
successful-correction eligibility is satisfied instead by the complete
exact-head convergence checkpoint for an unresolved required correction.

### Treat the policy as a revisitable operational experiment

This decision does not claim that convergence will shorten every loop, choose
the best stopping point, prevent regression, or improve every future PR.
Focused implementation proves coherent authority, routing, and truthful
records only. Later ordinary use may support retaining, refining, replacing,
or reverting this policy through another focused governance decision.

No trial period, success percentage, statistical validation, or fixed
observation window is required.

## Consequences

### Positive

- Independent review can retain maximum sensitivity without owning loop
  duration.
- The Adjudicator can judge accumulated correction value rather than only one
  finding inventory.
- A truthful RC can converge without routine owner intervention.
- Named required corrections and regression risks remain visible at merge.
- Acceptance does not silently create future work.
- The governance mechanism can itself be revised or reverted after use.

### Costs

- A converged candidate may be worse than another attainable correction.
- Critical or High findings may remain intentionally unresolved.
- Chain reconstruction adds a small adjudication input and Issue-record cost.
- The same implementation agent may assume the Adjudicator role, so the
  mutation freeze and durable checkpoint remain important.
- Operational experience, not this ADR, determines whether the experiment is
  useful.

## Rejected alternatives

### Reduce independent-review sensitivity

Rejected because hiding findings removes evidence instead of deciding what to
do with it.

### Add a separate convergence runtime role

Rejected because correction-loop outcome is an extension of existing product
adjudication, not a new evidence or mutation responsibility.

### Require non-regression or a mandatory quality threshold

Rejected because the owner explicitly accepts an experiment that may regress,
and a strict stopping theorem would recreate the loop it is intended to bound.

### Stop after a fixed number of reviews

Rejected because review count, finding count, severity, elapsed time, and diff
size do not determine whether another correction is selected.

### Create follow-up work for every residual

Rejected because acceptance ends the current obligation. Future work requires
new material evidence and its own selected scope.

### Keep owner waiver as the only way to stop with required corrections

Rejected because it leaves the Adjudicator unable to make the chain-level
product judgment introduced by this decision.
