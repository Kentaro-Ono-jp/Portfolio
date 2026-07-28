# Ready and merge workflow

<!-- ips-role: procedure -->
<!-- ips-rule: merge-workflow -->

## Read when

Read this file after independent review approves the current exact head, or the
owner explicitly accepts the exact verdict's named residual findings, and the
required proof is successful or machine-qualified.

## Procedure

1. Use [live-state exact checks](../references/live-state.md), return here, and
   require the live PR head, reviewed head, and intended merge target to agree.
2. Require either an `Approved` verdict for that head or a durable owner waiver
   that preserves the real verdict URL, names every accepted residual, pins the
   exact head, and explicitly authorizes merge. Never infer or manufacture a
   waiver.
3. Require successful exact-head Actions proof or the complete qualified
   Markdown-only exception.
4. Pin merge to the reviewed head and use the repository's established merge
   method.
5. Change Draft to Ready and merge the pinned exact head without a separate
   confirmation pause.
6. For a Markdown-only squash, read the
   [exception's squash boundary](../ci/exceptions/markdown-only.md#squash-merge-boundary),
   return here, and supply the explicit subject and body it requires.
7. Record the exact merge commit. Do not reconcile checklists or delete
   branches in this state.

## Recovery

- A moved head or superseded verdict returns to publication and exact-head
  review.
- A waiver that omits the verdict, residuals, exact head, or explicit merge
  authorization returns to correction; do not broaden it by inference.
- Missing proof returns through the
  [CI router](../ci/router.md).
- A merge-method discrepancy uses live-state recovery and the repository's
  current established method; never guess or broaden the merge target.
- If exact merge preconditions remain unproved, defer the merge mutation and
  preserve the approved or owner-waived checkpoint without a confirmation
  pause.

## Next

After a successful merge, open [reconcile](reconcile.md).
