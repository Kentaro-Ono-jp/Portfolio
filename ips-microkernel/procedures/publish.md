# Publish workflow

<!-- ips-role: procedure -->
<!-- ips-rule: publication-workflow -->

## Read when

Read this file when a complete first-pass candidate is verified and staged, or
after a correction must be committed and pushed to an existing Draft PR.

## Initial publication

1. Inspect the complete staged diff and staged file list.
2. Use [live-state exact checks](../references/live-state.md), return here, and
   require the intended branch, focused base, and expected remote tip.
3. Commit the complete verified candidate tersely without pushing.
4. Enter the [CI router](../ci/router.md), complete Gate A pre-CI / pre-push
   hardening against that exact local commit, and return here. If hardening
   moves local HEAD, Gate A restarts before publication continues.
5. Push only the exact checked HEAD and open a Draft PR linked to the focused
   Issue and governing tracking Issue. Read back the remote branch tip and live
   PR head; require both to equal the full pushed SHA.
6. Treat the pushed commit and Draft PR as the recoverable task checkpoint.
   Uncommitted or unpushed work is not durable handoff state.
7. Require the workflow result to target the exact pushed head. A different
   pushed SHA makes older CI, verdict, and endpoint evidence stale.
8. Complete Gate B by reading only triggered `pre-review` entries in the
   [Behavior careless-mistake guide](../knowledge/behavior.md). Compare the
   live PR base/head, exact-head workflow, and lifecycle links with the PR.
9. Reconcile the PR description with current scope, non-targets, failure model,
   acceptance criteria, selected/executed/carried/skipped groups and both N/NN
   counts, exact full base and head SHAs, exact-head workflow state, and any
   `Knowledge write-back` correction decision.
10. Read the live title and description back. Require both declared endpoints
    to equal the live PR endpoints and confirm that the metadata update did not
    move the PR head.
11. Supply a copyable initial-review prompt with repository, PR, governing
    tracking Issue, focused Issue, expected full base SHA, expected full head
    SHA, review cycle `initial`, previous verdict `none`, and current workflow
    evidence or qualified limitation. Dispatch only after Gate B passes.

## Follow-up push

For every correction, repeat Gate A before push. After the exact correction
push and its successful CI:

1. Read the remote branch and live PR head back and require both to equal the
   full pushed SHA.
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
7. Complete Gate B through triggered `pre-review` Behavior entries, then read
   the live description back and require its declared exact base and head to
   match the live endpoints.
8. Supply a refreshed initial-review prompt when no verdict exists; otherwise
   supply a re-review prompt with expected full base and head SHAs, the real
   previous-verdict URL, every finding disposition, correction links, and the
   direct knowledge write-back decision.

A pushed checkpoint is incomplete without the applicable populated prompt.
Editing only PR title or body is head-neutral and may reuse successful
exact-head CI. If Gate B requires a repository-file change, return to
implementation, commit it, repeat Gate A, push, and obtain new exact-head CI.

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
- Return any Gate B repository-file correction through Gate A and new CI.
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
