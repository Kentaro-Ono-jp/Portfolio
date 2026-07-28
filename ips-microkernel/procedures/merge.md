# Ready and merge workflow

<!-- ips-role: procedure -->
<!-- ips-rule: merge-workflow -->

## Read when

Read this file after independent review approves the current exact head and its
required proof is successful or machine-qualified.

## Procedure

1. Use [live-state exact checks](../references/live-state.md), return here, and
   require the live PR head, reviewed head, and intended merge target to agree.
2. Require successful exact-head Actions proof or the complete qualified
   Markdown-only exception.
3. Pin merge to the reviewed head and use the repository's established merge
   method.
4. Change Draft to Ready and merge the pinned exact head without a separate
   confirmation pause.
5. For a Markdown-only squash, read the
   [exception's squash boundary](../ci/exceptions/markdown-only.md#squash-merge-boundary),
   return here, and supply the explicit subject and body it requires.
6. Record the exact merge commit. Do not reconcile checklists or delete
   branches in this state.

## Recovery

- A moved head or superseded verdict returns to publication and exact-head
  review.
- Missing proof returns through the
  [CI router](../ci/router.md).
- A merge-method discrepancy uses live-state recovery and the repository's
  current established method; never guess or broaden the merge target.
- If exact merge preconditions remain unproved, defer the merge mutation and
  preserve the approved checkpoint without a confirmation pause.

## Next

After a successful merge, open [reconcile](reconcile.md).
