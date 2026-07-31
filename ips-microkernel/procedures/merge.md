# Ready and merge workflow

<!-- ips-role: procedure -->
<!-- ips-rule: merge-workflow -->

## Read when

Read this file after independent review approves the current exact head,
complete adjudication records zero required corrections, or the owner
explicitly accepts every named required correction for the exact reviewed
head, every reusable candidate has complete curation, and the required proof is
successful or machine-qualified.

## Procedure

1. Use [live-state exact checks](../references/live-state.md), return here, and
   require the live PR head, reviewed head, and intended merge target to agree.
2. Require exactly one valid outcome for that head:
   - an `Approved` verdict;
   - a complete focused-Issue adjudication that preserves the real RC URL,
     exact head, every finding and disposition, all accepted residuals, and
     records zero required corrections;
   - a durable owner waiver that preserves the real verdict URL and
     adjudication checkpoint, names every accepted required correction and
     residual, pins the exact head, and explicitly authorizes merge.
   Never infer or manufacture a disposition or waiver, and never relabel RC as
   Approved.
3. Require successful exact-head Actions proof or the complete qualified
   Markdown-only exception.
4. Require one complete curation checkpoint for every reusable candidate in
   the applicable verdict and correction chain. Every
   `promote-current-pr` checkpoint must be implemented in this exact reviewed
   head. A pending, stale, or unimplemented promotion cannot reach merge.
5. Pin merge to the reviewed head and use the repository's established merge
   method.
6. Change Draft to Ready and merge the pinned exact head without a separate
   confirmation pause.
7. For a Markdown-only squash, read the
   [exception's squash boundary](../ci/exceptions/markdown-only.md#squash-merge-boundary),
   return here, and supply the explicit subject and body it requires.
8. Record the exact merge commit. Do not reconcile checklists or delete
   branches in this state.

## Recovery

- A moved head or superseded verdict returns to publication and exact-head
  review.
- An incomplete or stale finding disposition returns to
  [adjudication](adjudicate.md).
- Pending, stale, or unimplemented candidate curation returns to
  [knowledge curation](curate-knowledge.md).
- A waiver that omits the verdict, adjudication, required corrections,
  residuals, exact head, or explicit merge authorization returns to
  correction; do not broaden it by inference.
- Missing proof returns through the
  [CI router](../ci/router.md).
- A merge-method discrepancy uses live-state recovery and the repository's
  current established method; never guess or broaden the merge target.
- If exact merge preconditions remain unproved, defer the merge mutation and
  preserve the approved or owner-waived checkpoint without a confirmation
  pause.

## Next

After a successful merge, open [reconcile](reconcile.md).
