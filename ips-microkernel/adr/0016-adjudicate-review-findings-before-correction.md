# ADR-0016: Adjudicate review findings before correction

- Status: Accepted
- Date: 2026-07-30
- Deciders: ReactorFront
- Amends: ADR-0014 review-outcome authority and the ADR-0008 lifecycle
- Related: ADR-0008, ADR-0009, ADR-0010, ADR-0014, Issue #48

## Context

Independent review is intentionally optimized for inspection depth, finding
recall, and exact evidence. That sensitivity is valuable, but the existing
implementation lifecycle gave an actionable `Changes requested` verdict only
two ordinary outcomes: correct every finding or invoke the repository owner's
exact-head waiver.

That coupling allowed a reviewer to influence product outcome beyond its
evidence role. A Medium or lower finding could become a correction mandate
even when a competent human team could discover and repair it later, the
correction would add disproportionate explanation cost, or the concern was
theoretical and did not materially improve product quality. Repeated review
then risked replacing human product judgment with AI completeness seeking.

Lowering reviewer capability would hide useful evidence. Letting the
implementation agent silently dismiss findings would create an unreviewed
conflict of interest. Using owner waiver for every non-correction decision
would make a strong exception the routine path.

The lifecycle needs a separate state that preserves maximum review and
implementation capability while deliberately applying human-scale product
judgment to finding disposition.

## Decision

### Add a Review Adjudicator runtime role

Add a Review Adjudicator between an exact-head `Changes requested` verdict and
correction or merge.

The implementation agent may assume this role in the same task, but only by
entering its dedicated procedure. While adjudicating, it freezes the reviewed
candidate and does not modify implementation, move the PR head, or rewrite the
review verdict. This is runtime role separation, not necessarily a separate
agent or task.

The independent reviewer remains isolated, evidence-maximizing, and limited to
one verdict comment. It does not adjudicate, edit the focused Issue, correct
implementation, or merge.

### Make actual Critical or High design breakage mandatory

For every finding, the adjudicator validates the cited evidence against the
exact reviewed head, focused Issue, and accepted design. Reviewer-supplied
severity is evidence, not binding authority.

A finding is `required-correction` when its proved effect materially breaks
Issue-defined accepted product design at Critical or High impact. That
threshold cannot pass through ordinary human-scale acceptance. If a
reviewer-labelled Critical or High finding does not prove that threshold, the
adjudicator records the lower actual impact and rationale before applying the
remaining model.

### Apply three human-scale lenses below the mandatory threshold

Every finding below the mandatory threshold receives one holistic judgment
that explicitly addresses all three lenses:

1. **Human discoverability and bounded recoverability:** whether a competent
   human operator or maintainer can realistically observe the problem and
   repair it through bounded work. Hidden, irreversible, or operationally
   unbounded effects support correction; ordinary discovery and recovery
   support acceptance.
2. **External technical explanation cost:** whether the correction can be
   explained externally at ordinary-or-lower cost as a technical strength.
   Disproportionate mechanism or explanation burden without corresponding
   product value supports acceptance.
3. **Material product-quality effect:** whether the correction improves a
   reachable product outcome rather than satisfying a theoretical,
   speculative, or corner-only concern. Proved material improvement supports
   correction; an unproved quality effect supports non-material treatment.

Do not reduce the lenses to a numeric score, vote, or mechanical
all-or-nothing rule. The adjudicator records a reasoned overall disposition:

- `required-correction`: the implementation must change before ordinary merge;
- `accepted-residual`: the finding is real but current product judgment does
  not select correction;
- `non-material`: the evidence does not establish a material defect in the
  accepted slice.

### Record disposition before mutation

Before correction or merge, append one adjudication checkpoint to the focused
Issue. It records:

- the exact reviewed head and stable real-verdict URL;
- every finding and its stable evidence;
- reviewer severity and adjudicated actual impact;
- all three Medium-or-lower lens judgments where applicable;
- one disposition and rationale for every finding;
- the aggregate required corrections and accepted residuals.

An adjudication applies only to its exact reviewed head. A correction produces
a new candidate that requires new exact-head proof and independent re-review.
The original RC remains RC and is never relabelled as Approved.

### Route by disposition

An Approved exact head bypasses adjudication and follows the existing merge
path.

A `Changes requested` exact head with incomplete finding disposition must
enter adjudication before any correction. One or more
`required-correction` outcomes route to correction. A complete adjudication
with zero required corrections may route to merge with the real RC and
accepted residuals preserved, without routine owner waiver.

Owner waiver remains the strong exception for explicitly accepting a named
required correction or otherwise overriding the normal adjudication boundary.
It retains ADR-0014's exact-head, real-verdict, residual, proof, and explicit
authorization requirements.

Reusable governance candidates remain separate evidence and continue through
the post-merge reconciliation defined by ADR-0009 and ADR-0010.

## Consequences

### Positive

- Reviewers can use maximum sensitivity without owning product outcome.
- Implementation does not begin before finding value is deliberately judged.
- Critical and High breakage of accepted product design remains mandatory.
- Medium and lower findings receive realistic human product-development
  judgment rather than automatic correction.
- RC remains honest while routine non-correction no longer requires a strong
  owner waiver.
- ADR-0014's non-monotonic policy gains a dedicated executable decision role.

### Costs

- Every RC with findings adds one bounded Issue-writing and disposition step.
- Human-scale lenses require judgment and cannot be made fully mechanical.
- The same implementation agent may assume adjudication and implementation
  roles, so the mutation freeze and pre-implementation record must be enforced.
- Accepted residuals remain visible product limitations rather than hidden
  approvals.

## Rejected alternatives

### Reduce independent-review sensitivity

Rejected because suppressing findings loses evidence instead of judging its
product value.

### Correct every RC finding

Rejected because review evidence is not automatic ownership authority and
AI-completeness work can reduce delivery speed without material quality gain.

### Let the implementer dismiss findings while correcting

Rejected because implementation-time dismissal is not a distinct,
inspectable decision boundary.

### Require owner waiver for every non-correction

Rejected because a strong exception should remain available for required
corrections, not serve as the routine Medium-or-lower disposition path.

### Use a numeric triage score

Rejected because the three lenses have contextual direction and cannot be
faithfully reduced to arithmetic.
