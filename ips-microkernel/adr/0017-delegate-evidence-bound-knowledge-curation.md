# ADR-0017: Delegate evidence-bound knowledge curation

- Status: Accepted
- Date: 2026-07-31
- Deciders: ReactorFront
- Amends: ADR-0009 and ADR-0014 recurrence-prevention selection
- Related: ADR-0010, ADR-0013, ADR-0016, Issue #52

## Context

ADR-0009 and ADR-0010 preserve every reusable governance candidate from
independent review and reconcile the complete candidate queue after merge.
ADR-0014 made recurrence prevention owner-selected so one incident could not
silently accumulate another permanent restriction.

That boundary prevents unwanted work, but it also makes the repository owner a
routine classifier for an iPS Microkernel capability that should operate from
stable evidence. A candidate can already retain its exact verdict, correction,
proof, and merge chain. Waiting until after merge also makes a causally related,
bounded rule more likely to become a separate follow-up even when it could have
been reviewed with the implementation that proved it.

Giving the independent reviewer or implementation role promotion authority
would collapse evidence, decision, and mutation into one actor. Promoting every
Critical or High finding would confuse current product impact with reusable
process value and steadily expand runtime context.

The lifecycle needs a distinct decision role that can discard weak candidates,
preserve promising ones, and promote a proved bounded rule without routine
owner selection.

## Decision

### Add a Knowledge Curator runtime actor

Add a **Knowledge Curator** after stable candidate evidence and applicable
finding disposition and correction proof are complete.

The implementation agent may enter this role in the same task only through its
dedicated procedure. While curating, it freezes the candidate, source verdict,
current PR head, correction chain, and proof. It may write one complete
curation checkpoint to the focused Issue and create or link the one deferred or
follow-up Issue required by its disposition. It does not review, implement,
move the PR head, or merge.

Independent review remains evidence-maximizing and mutation-isolated. Review
Adjudication continues to decide the current finding's product disposition.
Implementation applies only the rule selected by a completed curation
checkpoint. Final independent review and exact-head proof remain mandatory.

### Require evidence-bound curation

A reviewer severity label does not establish reusable value. Curation requires:

- one atomic candidate with stable source evidence;
- complete disposition for any associated actionable finding;
- successful proof of every required correction or a qualified exception;
- one canonical target selected by the governance knowledge selector;
- comparison with the existing rule and executable guards;
- a reasoned judgment that future behavior changes enough to justify the
  additional context and maintenance cost.

One occurrence may justify promotion when the gap is hidden, expensive,
irreversible, or not bounded by an existing guard. A visible failure that an
existing guard catches cheaply may be discarded even when its current product
impact required correction.

### Record one explicit disposition

Every atomic candidate receives exactly one disposition:

- `discarded`: product-specific, one-off, obvious, or not worth permanent
  context;
- `already-represented`: an existing canonical rule or executable guard owns
  the signal;
- `promote-current-pr`: a bounded, causally related rule with one canonical
  home is added to the current focused PR;
- `promote-follow-up`: the rule is reusable but late, cross-boundary, or too
  broad for the current focused PR;
- `deferred`: the signal is promising but needs a named recurrence or evidence
  trigger;
- `unclassified`: no honest canonical target or disposition is yet available.

`discarded` is a terminal judgment but its source evidence remains recoverable.
`deferred` and `unclassified` create or reuse one open GitHub Issue whose title
starts with `[Knowledge candidate]`, and whose body records the signal key,
stable evidence, origin, disposition, and exact resurfacing trigger. This live
state is searched only during later curation for the same signal key. It is not
a tracked or eagerly loaded incident ledger.

### Prefer promotion in the current PR

`promote-current-pr` is the default when the candidate is causally derived from
the current slice, the canonical target is known, and the rule does not
materially redefine product, delivery, architecture, security, or actor
authority.

The curator records its checkpoint before implementation mutation. The
implementation role then adds the selected rule and preferably an executable
guard to the same branch. That mutation invalidates older exact-head proof and
review. The complete changed head must be pushed, proved, and independently
reviewed before Squash merge.

Use `promote-follow-up` after merge, when an otherwise approved merge should
remain frozen, or when the rule crosses the current focused boundary. The
Knowledge Curator may create the bounded focused governance Issue without
routine owner selection. Material product, delivery, architecture, security,
or actor-authority redefinition still returns to focus for owner selection.

### Keep late reconciliation

Post-merge governance reconciliation remains responsible for cleanup,
recovery, evidence, and other late signals, and for verifying that every
pre-merge candidate has one complete curation outcome. It routes any new late
candidate through the same Knowledge Curator. A post-merge candidate cannot use
`promote-current-pr`.

### Guard the delegated route

Documentation verification owns the actor boundary, exact curation route,
evidence threshold, six dispositions, same-PR invalidation and re-review rule,
deferred live-state contract, and post-merge fallback. Focused mutation tests
must reject removal or weakening of each boundary independently.

## Consequences

### Positive

- The iPS Microkernel can improve its own collaboration rules from proved
  evidence without routine owner latency.
- Review, product adjudication, knowledge judgment, implementation, and final
  approval remain distinct runtime states.
- Causally related rules normally ship with the implementation that proved
  them.
- Weak observations can be explicitly discarded instead of accumulating.
- Deferred candidates remain recoverable without entering normal startup
  context.

### Costs

- A promoted same-PR rule adds another proof and review cycle after the head
  changes.
- Curation requires judgment about generality, context cost, and existing
  guards.
- Deferred candidate Issues require bounded live-state maintenance.
- Role and route verification become more detailed.

## Rejected alternatives

### Keep routine owner selection

Rejected because evidence-bound collaboration knowledge is a delegated runtime
responsibility, while owner attention remains reserved for material slice and
design decisions.

### Promote every blocking finding

Rejected because current product severity does not prove reusable value.

### Let the reviewer or implementer promote directly

Rejected because it collapses evidence, judgment, and mutation authority.

### Reconcile only after merge

Rejected because a bounded rule should normally share the final exact-head
proof and independent review of the PR that produced it.

### Add a tracked lessons ledger

Rejected because it duplicates canonical rules and consumes unrelated runtime
context.
