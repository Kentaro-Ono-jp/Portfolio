# Post-merge reconciliation workflow

<!-- aios-role: procedure -->
<!-- aios-rule: reconciliation-workflow -->

## Read when

Read this file only after a focused PR has merged and post-merge proof,
evidence reconciliation, or scoped cleanup remains.

## Procedure

1. Fast-forward clean local `main` to the exact merge commit without reset or
   discarded changes.
2. Inspect the exact merge message. Require its automatic `push` workflow to
   pass for that SHA unless the qualified Markdown-only exception applies.
3. For the exception, require the intended skip instruction and confirm no run
   exists. Do not dispatch, rerun, or create a trigger commit.
4. Enter the [CI router](../ci/router.md), select
   post-merge knowledge reconciliation, and return here with its outcome.
5. Open [governance knowledge reconciliation](governance-reconcile.md), record
   its exact outcome in the focused Issue, and return here.
6. Read the [Issue evidence reference](../references/evidence.md), reconcile
   only fully proved focused and governing tracking-Issue criteria, then return
   here.
7. Remove verified task-owned temporary data and a local branch only after its
   exact tip is proved fully merged.
8. Delete the remote branch only when the PR is merged, its remote tip equals
   the reviewed merged head, and no open PR references it. Otherwise retain it,
   record why, and continue reconciliation.

## Recovery

- Dirty state or a wrong merge SHA uses live-state recovery.
- Failed or missing main proof routes through the
  [CI router](../ci/router.md); do not mark affected
  evidence complete.
- Unresolved reusable CI knowledge remains an explicit reconciliation outcome.
- Unresolved reusable governance knowledge remains linked or unclassified; it
  is never copied into a nearby canonical rule.
- Contradictory or incomplete evidence leaves affected criteria unchecked and
  records the exact gap.
- Cleanup whose ownership or exact target cannot be proved is retained and
  reported without blocking proved evidence reconciliation.

## Next

When proof, evidence reconciliation, and scoped cleanup are complete, end this
slice. A later feature begins again at the [AIOS work router](../work-router.md).
