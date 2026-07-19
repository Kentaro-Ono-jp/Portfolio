# GitHub evidence and checklist policy

Issue checkboxes are evidence-backed delivery records. A green PR check,
automatic Issue closure, or elapsed time is not enough to mark acceptance
criteria complete.

## Focused Issues

Reconcile a focused Issue only after its implementing PR has merged and the
exact merge commit has passed the default-branch workflow.

For every criterion, map the claim to concrete evidence such as:

- the merged PR, reviewed head, and merge commit
- the final independent verdict
- exact-head PR and exact-merge main workflow runs
- unit, static, integration, runtime, recovery, and failure-path results
- retained failure artifacts and successful scoped teardown
- documentation, boundary, and explicit non-target audits

Check only criteria that are fully proved. Leave an unproved criterion
unchecked and record what is missing even when the focused Issue is already
closed.

When all criteria are proved:

- check them in the Issue body
- convert planned-branch wording to implemented history where useful
- append a `Completion evidence` section with stable links and exact SHAs
- preserve the original scope, failure model, non-targets, and definition of
  done

## Umbrella Issue #1

Issue #1 is the live ledger for the complete vertical slice. After every
relevant merge, add the completed focused increment and its review, merge, and
workflow evidence.

Re-evaluate each umbrella gate, but check it only when accumulated evidence
proves every acceptance criterion for that entire Delivery Specification step
or an explicit approved exception is documented. A focused PR may contribute
partial evidence without completing a gate; state the remaining work and keep
the box unchecked.

Check the final delivery-record item only after the delivery specification
records its completion date, implementation PRs, final workflow, known
limitations, and follow-up slices.

If later live evidence invalidates a checked gate, uncheck it or annotate the
regression until it is proved again.

## Review and mutation authority

The independent review agent may publish a verdict comment but does not edit
Issue checklists. The implementation agent performs post-merge reconciliation
only with owner authorization and after exact-target verification.

## Link and privacy requirements

Use stable GitHub links and exact full SHAs where they matter. Evidence must
not contain credentials, raw private input, personal facts, local absolute
paths, or private company and client context.
