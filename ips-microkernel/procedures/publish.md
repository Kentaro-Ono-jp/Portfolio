# Publish workflow

<!-- ips-role: procedure -->
<!-- ips-rule: publication-workflow -->

## Read when

Read this file when a complete candidate is verified, CI-hardened, and staged,
or after a correction must be pushed to an existing Draft PR.

## Initial publication

1. Inspect the complete staged diff and staged file list.
2. Use [live-state exact checks](../references/live-state.md), return here, and
   require the intended branch and head.
3. Commit tersely, push the focused branch, and open a Draft PR linked to the
   focused Issue and governing tracking Issue.
4. Treat the pushed commit and Draft PR as the recoverable task checkpoint.
   Uncommitted or unpushed work is not durable handoff state.
5. Require the workflow result to target the exact pushed head.
6. Reconcile the PR description with current scope, non-targets, failure model,
   acceptance criteria, selected/executed/carried/skipped groups and both N/NN
   counts, exact head, and exact-head workflow state.
7. Read the live PR description back and require its declared head to equal the
   live PR head.
8. Supply a copyable initial-review prompt with repository, PR, governing
   tracking Issue, focused Issue, expected full SHA, review cycle `initial`,
   previous verdict `none`, and current workflow evidence or qualified
   limitation.

## Follow-up push

After every correction push:

1. Require the live PR head to equal the full pushed SHA.
2. Replace the current-review head and describe why it moved plus the exact
   delta from the previous head.
3. Record the previous verdict and every finding's disposition.
4. Record current-head local proof and exact-head workflow state as pending,
   successful, failed, or intentionally absent. Older runs are preceding or
   superseded, never current proof.
5. Restate the complete current skipped-group set in the exact-head
   `Verification-Skip` trailer, including inherited gaps not re-executed.
6. State whether scope, non-targets, failure model, or acceptance criteria
   changed.
7. Read the live description back and require its declared head to match.
8. Supply a refreshed initial-review prompt when no verdict exists; otherwise
   supply a re-review prompt with the real previous-verdict URL and every
   finding disposition.

A pushed checkpoint is incomplete without the applicable populated prompt.

## Conditional exception

When the complete candidate satisfies the
[machine-qualified Markdown-only CI exception](../ci/exceptions/markdown-only.md), read
it, return here, use its supported skip instruction, and include every required
exception field. An absent run is never passing proof.

## Recovery

- Reverify and restage a stale index.
- Return an unintended diff to implementation without discarding unrelated
  work.
- Refresh a moved remote head through live-state recovery.
- Rewrite and read back a stale PR description.
- Route missing exact-head proof through the CI router.
- Return a material scope change to [focus](focus.md) before publication
  continues.

## Next

- A proved reusable candidate with complete disposition for every associated
  actionable finding and proof for every required correction, but no complete
  curation checkpoint: open [knowledge curation](curate-knowledge.md).
- No verdict and no pending eligible candidate: start the independent review task at the
  [review router](../review/router.md).
- `Changes requested` with incomplete finding disposition: open
  [adjudicate](adjudicate.md).
- Complete adjudication with required corrections: open [correct](correct.md).
- Approved exact head, fully adjudicated exact head with zero required
  corrections, or exact reviewed head with a recorded owner waiver and
  required proof, after every candidate has complete curation: open
  [merge](merge.md).
