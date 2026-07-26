# ADR-0009: Reconcile reusable governance knowledge through reviewed updates

- Status: Accepted
- Date: 2026-07-26
- Deciders: ReactorFront
- Related: ADR-0008, Issue #34

## Context

ADR-0008 introduced progressive-disclosure routing and gave CI failures a
strong feedback loop: staged preflight and failed-run triage select one
knowledge leaf, and post-merge reconciliation promotes only a new reusable
runner rule.

The wider development lifecycle did not yet have an equally explicit write
path. Independent review, correction, live-state recovery, evidence
reconciliation, and cleanup can expose reusable process knowledge, but the
reviewer has permission for only one verdict comment and the post-merge
workflow previously said only to update guidance when the process changed.
That generic instruction did not classify the signal, select its canonical
owner, require a no-finding outcome, or make the promotion path executable.

Adding a general incident ledger would duplicate references and procedures,
eagerly load unrelated history, and weaken the one-canonical-home rule.

## Decision

### Capture without reviewer mutation

Independent inspection classifies any reusable process or review signal
separately from actionable findings. The single verdict comment records one
`Reusable governance candidate` section with exact evidence or `none`.

The candidate is not authority and does not by itself change guidance.
Reviewers retain the isolated-clone, static-only, one-comment, prohibited-write,
and verified-cleanup boundaries.

### Reconcile after every merge

After exact merged-main proof and CI knowledge reconciliation, the
implementation lifecycle audits only that focused slice's verdicts,
corrections, recovery, and reconciliation outcomes.

It separates:

- product defects and one-off observations
- CI runner knowledge, which returns to the existing CI knowledge route
- product or structural decisions, which return to focus and ADR or delivery
  change control
- reusable collaboration knowledge, which enters the governance selector

No reusable finding records
`Governance knowledge reconciliation: no new reusable finding` in the focused
Issue.

### Select one canonical destination

The governance selector is a thin router, not an append-only ledger. It assigns
one atomic root-cause signal key at a time, using ordered precedence, to an
existing canonical reference, lifecycle procedure, review procedure, CI route,
ADR index, or delivery index. A compound observation is split before
selection, so one candidate never receives two canonical targets.

The caller compares the candidate with the selected rule and executable guards.
It does not copy the same rule into a second destination.

Reconciliation processes an ordered candidate queue. Each candidate receives
and records one outcome before the workflow returns for the next candidate;
the aggregate no-finding outcome is decided only after queue exhaustion.

### Promote through focused review

A genuinely new reusable process rule requires an accepted focused governance
Issue and independently reviewed PR before repository guidance changes.
Initial or materially redefined scope still uses the sole owner-confirmation
boundary in focus.

When the current focused governance PR already contains and proves the exact
accepted update, reconciliation records that evidence and does not create a
recursive empty Issue. Otherwise it links the follow-up governance Issue from
the merged feature before the next feature increment.

### Protect the write route

Documentation verification owns the exact selector and procedure inventory,
route reachability, canonical markers, thin-router budget, reviewer candidate
field, no-finding outcome, focused-Issue and reviewed-PR promotion policy, and
CI/design rerouting text. It also verifies the complete ordered signal-key to
target mapping and rejects duplicate keys, wrong targets, and removal of the
multi-candidate loop.

## Consequences

### Positive

- Review knowledge survives the one-comment boundary without granting the
  reviewer mutation authority.
- Every reusable process signal has a deterministic canonical destination.
- CI and product knowledge remain in their existing systems.
- Empty knowledge churn is replaced by an explicit no-finding outcome.
- The write path is tested as strongly as the read topology.

### Costs

- Every feature merge performs one additional bounded reconciliation step.
- A material new governance rule may require a focused follow-up before the
  next feature increment.
- Candidate classification still requires judgment; exact evidence and
  independent review bound that judgment.
- Taxonomy changes require representative ambiguity and multiple-candidate
  negative regressions, not destination-inventory assertions alone.

## Rejected alternatives

- Give the reviewer permission to edit guidance directly.
- Add a single general review-lessons journal.
- Treat every review comment as reusable knowledge.
- Append process findings to CI history regardless of signal type.
- Keep the generic post-merge instruction without a selector or machine guard.
