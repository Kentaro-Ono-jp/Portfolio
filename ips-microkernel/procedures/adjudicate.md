# Review finding adjudication

<!-- ips-role: procedure -->
<!-- ips-rule: review-adjudication -->

## Read when

Read this file in the implementation lifecycle after an independent exact-head
`Changes requested` verdict contains findings whose disposition is incomplete.
An Approved verdict bypasses this procedure.

## Required inputs

- focused Issue with accepted outcome, scope, non-targets, failure model, and
  acceptance criteria
- exact reviewed PR head and current expected review head
- stable real-verdict URL
- every finding with reviewer severity and exact evidence
- required exact-head proof or its accurately recorded limitation

## Role boundary

The implementation agent may assume the **Review Adjudicator** role in the same
task, but it is a distinct runtime role. Freeze the reviewed candidate while
this role is active.

Do not modify implementation, move the PR head, begin correction, relabel the
verdict, or perform merge while adjudication is incomplete. The adjudicator
may make only the focused-Issue write needed to record its complete
disposition. It does not become the independent reviewer.

## Procedure

1. Use [live-state exact checks](../references/live-state.md), return here, and
   require the verdict SHA, live PR head, expected review head, verdict URL,
   and complete finding inventory to agree.
2. Judge each finding against the exact evidence, focused Issue, and accepted
   design. Reviewer severity is evidence, not binding authority.
3. Record `required-correction` when the proved effect materially breaks the
   Issue-defined accepted product design at Critical or High impact. Ordinary
   adjudication cannot accept that outcome without correction.
4. When that mandatory threshold is not proved, record the actual Medium-or-
   lower impact and make one holistic judgment that explicitly covers:
   - **human discoverability and bounded recoverability:** realistic human
     observation and bounded repair versus hidden, irreversible, or unbounded
     effect;
   - **external technical explanation cost:** ordinary-or-lower explanation as
     a technical strength versus disproportionate mechanism or explanation
     burden;
   - **material product-quality effect:** reachable, proved improvement versus
     a theoretical, speculative, or corner-only concern.
5. Do not use a numeric score, vote, or mechanical all-or-nothing rule. Assign
   exactly one disposition to every finding:
   - `required-correction`;
   - `accepted-residual`;
   - `non-material`.
6. Before any implementation mutation or merge, append one adjudication
   checkpoint to the focused Issue containing:
   - exact reviewed head and stable real-verdict URL;
   - every finding and its stable evidence;
   - reviewer severity and adjudicated actual impact;
   - all three lens judgments where the mandatory threshold was not met;
   - disposition and concise rationale for every finding;
   - aggregate required corrections and accepted residuals.
7. Read the focused Issue back and require the complete checkpoint to match
   the exact reviewed head and finding inventory.
8. If scope or accepted design must materially change, route to
   [focus](focus.md). Otherwise route by the recorded aggregate.

Reusable governance candidates remain separate evidence. Do not classify or
promote them while the Review Adjudicator role is active.

## Adjudication guards

- An untrusted, moved, incomplete, or mismatched verdict returns through
  [live-state recovery](../references/live-state.md); never infer a missing
  finding or disposition.
- Missing required exact-head proof returns through the CI route selected by
  the work router; adjudication does not convert an evidence gap into pass.
- A reviewer-labelled Critical or High finding may be recorded below the
  mandatory threshold only when exact evidence shows that it does not
  materially break Issue-defined accepted product design and the rationale is
  explicit.
- A Critical or High design-breaking `required-correction` may reach merge
  without correction only through ADR-0014's exact owner-waiver path.
- The real RC remains visible. A disposition is not an approval and never
  rewrites the verdict.
- Adjudication expires when the PR head moves.

## Next

- One or more `required-correction` dispositions and no exact owner waiver:
  open [correct](correct.md).
- Complete adjudication with zero required corrections, required proof, and one
  or more uncurated reusable candidates: open
  [knowledge curation](curate-knowledge.md).
- Complete adjudication with zero required corrections, required proof, and no
  pending candidate curation: open [merge](merge.md).
- Exact owner waiver accepts every named required correction: open
  [merge](merge.md).
- Material outcome, scope, non-target, or accepted-design change: open
  [focus](focus.md).
