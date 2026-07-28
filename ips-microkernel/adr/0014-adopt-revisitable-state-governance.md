# ADR-0014: Adopt revisitable-state and non-prohibitive change governance

- Status: Accepted
- Date: 2026-07-28
- Deciders: ReactorFront
- Amends: ADR-0009
- Related: ADR-0008, ADR-0009, ADR-0010, ADR-0011, ADR-0013, Issue #44

## Context

The iPS Microkernel already uses progressive disclosure for documentation and
verification. Its workflows nevertheless risked becoming monotonic: each
incident, failed review, or reusable candidate could accumulate another
permanent restriction, mandatory recurrence-prevention task, or merge blocker.

That behavior mistakes evidence for prohibition. A previous state may be
undesirable in one context and valid in another. An existing implementation
may need to be revised, replaced, reverted, or deliberately restored. A
breaking or destructive effect may be the intended and authorized result of a
focused change rather than a class of work the system must forbid.

Independent review also supplies evidence rather than ownership authority. A
`Changes requested` verdict must remain visible and must never be mislabeled,
but the repository owner may understand the residual risk and deliberately
accept it.

Selective CI needs the same distinction. A group that is not selected is not
silently ignored: it is either backed by applicable carried evidence or
reported as an explicit unproved gap. Selection reduces irrelevant execution,
not the honesty of the evidence record.

This ADR amends ADR-0009 only where that record made a reusable update
mandatory before the next feature increment. ADR-0009 remains historical
evidence; the current runtime rule is owner-selected recurrence prevention on
the follow-up Issue's own lifecycle.

## Decision

### Treat repository states as revisitable

Governance is non-monotonic. Leaving a state, fixing a defect, or rejecting an
approach does not permanently forbid returning to it.

Within an accepted focused slice, existing work may be revised, replaced,
reverted, or intentionally returned to a previously observed state. The
decision uses current scope and evidence rather than an inherited ban.

### Make recurrence prevention opt-in

An incident or review finding does not automatically create a
recurrence-prevention requirement.

Prevention work is part of the current slice only when the owner selects it in
the focused outcome. Reusable candidates are classified and recorded, but an
unselected follow-up does not block completion or the next feature increment.

### Do not ban destructive or breaking change by category

Destructive, breaking, replacement, and migration changes remain available
design choices.

This is not blanket mutation authority. Every concrete action still requires:

- accepted focused scope;
- an exact identified target;
- authority from the applicable actor;
- preservation of unrelated work;
- evidence proportionate to the effect;
- an explicit recovery path or recorded irreversible limitation.

The effect is judged in context. The category alone is not a prohibition.

### Allow an exact owner-waiver path

After an independent exact-head verdict, the repository owner may explicitly
accept named residual findings and authorize the reviewed head to merge without
further correction.

The durable checkpoint must record:

- the exact reviewed head;
- the real verdict and its stable URL;
- every residual finding being accepted;
- successful required proof or a qualified exception;
- the owner's explicit waiver and merge authorization.

The workflow may then route to merge. It must not rewrite `Changes requested`
as `Approved`.

### Treat selective CI as proof disclosure

The verification planner selects groups from changed paths, dependencies, and
evidence lineage.

- `selected` identifies proof required by the current candidate;
- `executed` identifies proof run against the current candidate;
- `carried` identifies successful unaffected proof inherited from a trusted
  baseline;
- `skipped without evidence` identifies an explicit gap and never means pass.

Missing lineage triggers conservative execution. Docker-backed groups use the
same model but execute authoritatively in GitHub Actions.

## Consequences

### Positive

- Governance does not accumulate permanent bans after every failure.
- Review evidence remains honest without granting reviewers ownership veto.
- Owners can accept bounded residual risk without fabricating approval.
- Destructive or breaking work remains possible when it is the selected
  outcome.
- Reusable candidates do not force unwanted follow-up work.
- Selective CI is explained as evidence allocation rather than reduced rigor.

### Costs

- Owner waivers require an explicit durable record.
- The same defect or state may recur by deliberate choice.
- Some accepted outcomes may retain known limitations.
- Exact target, authority, evidence, and recovery checks remain necessary for
  risky mutations.

## Rejected alternatives

### Permanently prohibit every previously failing state

Rejected because context changes and evidence does not create timeless
prohibition.

### Require recurrence prevention for every finding

Rejected because it expands focused work without an owner-selected outcome and
turns review observations into mandatory scope.

### Ban destructive or breaking changes

Rejected because replacement, migration, deletion, and compatibility breaks
can be legitimate intended outcomes.

### Treat an owner waiver as approval

Rejected because it corrupts the review record. The waiver authorizes the
decision while preserving the actual verdict.
