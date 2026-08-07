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
4. Enter the [CI router](../ci/router.md) and complete publication Gate A
   against that exact local commit. Gate A selects applicable CI Playbook
   leaves, reads them, and repairs test/proof scripts before remote push. If
   hardening moves local `HEAD`, commit the complete change and restart Gate A.
5. Push only the exact Gate-A-checked `HEAD` and open a Draft PR linked to the
   focused Issue and governing tracking Issue. Read back the remote branch tip
   and live PR head; require both to equal the full pushed SHA.
6. Immediately after that first push submits the head to GitHub Actions, the
   main implementation thread attempts `thread/compact/start` for its current
   thread when the host exposes that capability.
7. Treat the pushed commit and Draft PR as the recoverable task checkpoint.
   Uncommitted or unpushed work is not durable handoff state.
8. Require GitHub Actions to target and succeed for the exact pushed head. A
   different pushed SHA makes older CI, verdict, and endpoint evidence stale.
9. Reconcile the PR description with current scope, non-targets, failure model,
   acceptance criteria, selected/executed/carried/skipped groups and both N/NN
   counts, exact full base and head SHAs, exact-head workflow state, and any
   Stage A occurrence, Stage B rule, or CI Playbook record included in the
   candidate. Absence of an operational record needs no `none` placeholder.
10. Complete publication Gate B by executing every triggered rule in the
   [Implementation Prune Stage B checklist](../knowledge/behavior.md). Read the
   live title and description back, require declared endpoints to equal live
   PR endpoints, and confirm metadata repair did not move the PR head.
11. Supply a copyable initial-review prompt with repository, PR, governing
    tracking Issue, focused Issue, expected full base SHA, expected full head
    SHA, review cycle `initial`, previous verdict `none`, and current workflow
    evidence or qualified limitation. Dispatch only after Stage B passes.
12. Immediately after dispatching the initial-review subagent, the same main
    implementation thread attempts `thread/compact/start` for its current
    thread when the host exposes that capability.

Both compaction checkpoints are experimental and best-effort. Repository
guidance neither provides nor guarantees the App Server capability. An
unavailable tool, rejected request, or missed checkpoint does not invalidate CI,
review evidence, merge eligibility, or lifecycle completion.

CI Playbook reading and test/proof repair occur before `git push`. Never defer
them to the interval after push and before GitHub Actions starts.

## Follow-up push

For every repository correction:

1. Require the concrete correction to exist before operational recording.
   Append Stage A immediately for an implementation correction. After an
   adjudicated review correction, add or strengthen Stage B only when it yields
   a machine-decidable rule. After a CI correction, append a duplicate-allowed
   CI Playbook record without reading prior entries.
2. Verify, stage, and commit the complete correction plus applicable records.
3. Complete Gate A before remote push. Read selected CI Playbook leaves and
   repair test/proof scripts; if local `HEAD` moves, commit and restart Gate A.
4. Push the one exact checked correction head.
5. Immediately read the remote branch and live PR head back. Require both to
   equal the full pushed SHA before waiting for CI or continuing lifecycle.
6. Treat older CI, verdict, and endpoint evidence as stale whenever pushed SHA
   differs. A mismatch enters live-state recovery.
7. Require GitHub Actions to succeed for the exact read-back head.
8. Replace current-review head and describe why it moved plus the exact delta
   from the previous head. Record the previous verdict and every finding's
   disposition.
9. Record current-head local proof and exact-head workflow state as pending,
   successful, failed, or intentionally absent. Older runs are preceding or
   superseded, never current proof.
10. Restate the complete current skipped-group set in the exact-head
    `Verification-Skip` trailer, including inherited gaps not re-executed.
11. State whether scope, non-targets, failure model, or acceptance criteria
    changed, and list operational files changed without assigning proof status
    to their entries.
12. Execute Stage B, then read live PR metadata back and require its declared
    exact base and head to match live endpoints.
13. Supply a refreshed initial-review prompt when no verdict exists; otherwise
    supply a re-review prompt with expected full base and head SHAs, the real
    previous-verdict URL, every finding disposition, correction links, and
    current exact-head workflow evidence.

A pushed checkpoint is incomplete without the applicable populated prompt.

## Stage B correction boundary

When Stage B finds a repository-file problem whose repair moves `HEAD`, return
to implementation, correct it, append Stage A when applicable, complete Gate A
before one ordinary push, obtain new exact-head CI, and execute Stage B again.
Do not duplicate the Stage B rule that found the problem.

When Stage B finds a HEAD-neutral problem:

1. correct the live PR title, body, endpoints, or other neutral surface;
2. read the live value back and confirm the PR head is unchanged;
3. after correction, add or strengthen one deduplicated `neutral` Stage B rule
   with mechanical Detect, exact Pass, and concrete Repair text; and
4. execute Stage B again without requiring a push or CI run solely to certify
   the rule.

Editing only live PR metadata preserves successful exact-head CI. If
repository persistence of the Stage B rule later moves `HEAD`, ordinary
candidate Gate A, CI, and review apply to that changed head; they do not prove
the rule itself.

## Conditional exception

When the complete candidate satisfies the
[machine-qualified Markdown-only CI exception](../ci/exceptions/markdown-only.md),
read it, return here, use its supported skip instruction, and include every
required exception field. An absent run is never passing proof.

## Recovery

- Reverify and restage a stale index.
- Return an unintended diff to implementation without discarding unrelated
  work.
- Refresh a moved remote head through live-state recovery.
- Rewrite and read back stale PR metadata.
- Return a Stage B repository-file correction through Gate A and new CI.
- Route missing exact-head candidate proof through the CI router.
- Return a material scope change to [focus](focus.md).

## Next

- A proved reusable candidate with complete disposition for every associated
  actionable finding and proof for every required correction, but no complete
  curation: open [knowledge curation](curate-knowledge.md).
- No verdict and no pending eligible candidate: start the independent review
  task at the [review router](../review/router.md).
- `Changes requested` with incomplete finding disposition: open
  [adjudicate](adjudicate.md).
- Complete adjudication with required corrections: open [correct](correct.md).
- Approved exact head, fully adjudicated exact head with zero required
  corrections, or exact reviewed head with a recorded owner waiver and
  required proof, after every candidate has complete curation: open
  [merge](merge.md).
