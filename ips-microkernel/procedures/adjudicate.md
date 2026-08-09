# Review finding and correction-loop adjudication

<!-- ips-role: procedure -->
<!-- ips-rule: review-adjudication -->

## Read when

Read this file in the implementation lifecycle after an independent exact-head
`Changes requested` verdict contains findings whose disposition or aggregate
correction-loop decision is incomplete. An Approved verdict bypasses this
procedure.

## Required inputs

- focused Issue with accepted outcome, scope, non-targets, failure model, and
  acceptance criteria
- exact reviewed PR head and current expected review head
- stable real-verdict URL
- every current finding with reviewer severity and exact evidence
- applicable ordered chain of earlier reviewed heads, real verdict URLs,
  adjudication checkpoints, correction heads, and declared deltas
- required exact-head proof or its accurately recorded governed limitation

An initial review has a one-verdict chain. Never infer a missing head, verdict,
finding, disposition, correction, or delta.

## Role boundary

The implementation agent may assume the **Review Adjudicator** role in the same
task, but it is a distinct runtime role. No Convergence Adjudicator or other
runtime role exists. Freeze the reviewed candidate and applicable chain while
this role is active.

Do not modify implementation, move the PR head, begin correction, relabel the
verdict, or perform merge while adjudication is incomplete. The adjudicator
may make only the focused-Issue write needed to record its complete checkpoint.
It does not become the independent reviewer or reduce review sensitivity.

## Procedure

1. Use [live-state exact checks](../references/live-state.md), return here, and
   require the verdict SHA, live PR head, expected review head, verdict URL,
   current proof, and complete finding inventory to agree.
2. Freeze the applicable ordered review, adjudication, and correction chain.
   Require every recorded earlier head, stable verdict or checkpoint URL,
   correction head, and declared delta to agree with live durable evidence.
3. Judge each current finding against its exact evidence, focused Issue,
   accepted design, and applicable chain. Reviewer severity is evidence, not
   binding outcome authority.
4. Apply the carried-forward individual classification semantics before
   aggregate judgment:
   - a finding is `required-correction` when its proved effect materially
     breaks Issue-defined accepted product design at Critical or High actual
     impact;
   - when a reviewer-labelled Critical or High finding does not prove that
     threshold, record the lower actual impact and rationale before applying
     the remaining model; and
   - below that threshold, explicitly address human discoverability and
     bounded recoverability, external technical explanation cost, and material
     product-quality effect as three holistic lenses, never as a numeric score,
     vote, or mechanical all-or-nothing rule.
5. Assign exactly one individual disposition to every current finding:
   - `required-correction`;
   - `accepted-residual`;
   - `non-material`.
   A required correction meets the individual correction threshold; an
   accepted residual is real but current product judgment does not select
   correction; non-material evidence does not establish a material defect in
   the accepted slice.
6. Consider accepted scope and design, finding materiality, human
   discoverability and bounded recoverability, external technical explanation
   cost, material product-quality effect, marginal quality gain, added
   complexity, regression exposure, quota pressure, future flexibility, and
   present acceptance holistically. None is a mandatory veto, numeric score,
   vote, cycle cap, or mechanical threshold.
7. After every finding has a disposition, assign exactly one aggregate
   decision:
   - `continue-correction`: select one or more current
     `required-correction` findings for another ordinary correction and
     re-review cycle;
   - `converge`: accept the current exact head for curation and merge routing,
     even when required corrections, Critical or High reviewer severity,
     possible quality improvement, or known regression risk remains.
8. Before any implementation mutation or merge, append one adjudication
   checkpoint to the focused Issue containing:
   - exact reviewed head and stable real-verdict URL;
   - applicable ordered review, adjudication, and correction-chain summary;
   - every current finding, its stable evidence, reviewer severity, actual
     impact judgment, individual disposition, and concise rationale;
   - unresolved required corrections, accepted residuals, and known regression
     risk;
   - exactly one `continue-correction` or `converge` decision; and
   - concise reason why another correction is or is not selected.
9. Read the focused Issue back and require the complete checkpoint to match the
   exact reviewed head, finding inventory, chain identity, and aggregate
   decision.
10. If outcome, scope, non-targets, or accepted design itself must materially
   change, route to [focus](focus.md). Recorded acceptance of a current
   residual or regression does not by itself rewrite the focused Issue.

Reusable governance candidates remain separate evidence. Do not classify or
promote them while the Review Adjudicator role is active. An accepted residual
creates no follow-up Issue, backlog item, deadline, assigned action, or promise
of later correction.

## Adjudication guards

- An untrusted, moved, incomplete, or mismatched verdict or chain returns
  through [live-state recovery](../references/live-state.md); never infer a
  missing finding, disposition, correction, or aggregate decision.
- Missing required exact-head proof returns through the CI route selected by
  the work router. Adjudication may preserve a governed limitation but does not
  manufacture a pass.
- No severity, materiality class, review count, finding count, elapsed time,
  token use, diff size, or quality claim automatically requires or prohibits
  convergence.
- `converge` may retain named `required-correction` findings and known
  regression risk without owner waiver. It is not proof of optimality, safety,
  non-regression, or future effectiveness.
- The real RC remains visible. A finding disposition or aggregate decision is
  not an approval and never rewrites the verdict.
- Adjudication and convergence evidence expire when the PR head or recorded
  correction-chain identity changes.

## Next

- `continue-correction` with selected required corrections and no exact owner
  waiver: open [correct](correct.md).
- `converge` with one or more uncurated reusable candidates: open
  [knowledge curation](curate-knowledge.md).
- `converge` with complete candidate curation and required proof: open
  [merge](merge.md), whether or not required corrections remain.
- Exact owner waiver overrides a recorded `continue-correction` decision: open
  [merge](merge.md).
- Material outcome, scope, non-target, or accepted-design change: open
  [focus](focus.md).
