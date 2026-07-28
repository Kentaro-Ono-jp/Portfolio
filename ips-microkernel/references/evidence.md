# Issue and delivery evidence reference

<!-- ips-role: reference -->
<!-- ips-rule: issue-evidence -->

## Read when

Read this file only after merge when exact default-branch proof or the
machine-qualified Markdown-only exception permits evidence reconciliation.

## Focused Issue

Reconcile only after the implementing PR is merged and the exact merge commit
passes the default-branch workflow or satisfies the qualified Markdown-only
exception.

- Map every acceptance criterion to implementation, review, PR-run, main-run,
  failure-path, scope, and cleanup evidence as applicable.
- Check a criterion only when it is fully proved or the owner explicitly
  accepts its named residual gap. An owner-accepted criterion must link the
  residual evidence and state that acceptance is a waiver rather than proof.
  Otherwise leave it unchecked and record what is missing, even if the Issue
  is already closed.
- When all criteria are proved or explicitly owner-accepted, preserve the
  original scope, failure model, non-targets, and definition of done, then add
  `Completion evidence` with stable links, exact SHAs, and every waiver.

## Governing tracking Issue

After every relevant merge, add accumulated proof to the tracking Issue linked
from the governing delivery specification.

Check an umbrella gate only when evidence proves every acceptance criterion for
the complete Delivery Specification step or a qualified exception. Partial
proof remains attached while the gate stays unchecked.

Check the final delivery-record item only after the delivery specification
records its completion date, implementation PRs, final workflow, known
limitations, and follow-up slices. If later evidence invalidates a checked
gate, uncheck it or annotate the regression until it is proved again.

The independent reviewer never edits Issue checklists.

## Return

Return to post-merge reconciliation with the exact Issue changes made and any
unproved criteria identified.
