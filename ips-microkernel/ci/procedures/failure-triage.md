# Failed-run triage and correction recording

<!-- ips-role: procedure -->
<!-- ips-rule: ci-failure-triage -->

## Read when

Read this file only after an exact-head GitHub Actions run fails.

## Procedure

1. Pin the exact PR head and failed run.
2. Read the failing step, retained artifacts, and first causal service error
   before reacting to teardown noise.
3. Classify the signal as product semantics, dependency or image parity,
   invocation portability, identity, framework runtime, persistence, state
   isolation, messaging, browser, readiness or recovery, or evidence and
   cleanup.
4. Diagnose from accepted design, the exact candidate, and the failed run. Do
   not preload CI Playbook history before the concrete correction.
5. Reproduce only through safe non-Docker local checks or GitHub Actions. Never
   start local Docker because Actions failed.
6. Fix the root cause and add the smallest executable regression protection.
7. After the complete correction exists, append the current PR occurrence
   through the [Stage A ledger](../../knowledge/correction-ledger.md) when the
   failure exposed an implementation mistake.
8. After the correction exists, use the
   [CI Playbook selector](../knowledge/selector.md) only to choose one append
   target. Append Origin, Trigger, Mistake, and Correction without scanning or
   deduplicating prior entries. Duplicate records are allowed. Do not require
   Evidence, successful CI, review, merge, a proof state, or a dedicated proof
   push.
9. Run allowed canonical verification, commit the complete corrected candidate
   and records, then return through publication Gate A. Gate A reads selected
   CI Playbook leaves and repairs test/proof scripts before one ordinary remote
   push. Require the next exact workflow result.

Do not write an unresolved symptom or pre-correction guess. Do not update Stage
B for a CI failure. Do not add compatibility flags merely to make a pinned
service accept obsolete behavior. Remove unused topology or correct the
application contract. Do not replace bounded readiness polling with an
unexplained fixed sleep.

## Recovery

- Refresh a moved head and re-pin the exact failed run.
- Rerun an unchanged exact head once when causal evidence was unavailable.
- Route material scope or design change to [focus](../../procedures/focus.md).
- Move unsafe or environment-dependent reproduction to GitHub Actions.
- Reject a workaround that weakens accepted proof and continue root-cause
  analysis from the last exact checkpoint.

## Next

- Corrected implementation returns to its implementation and publication
  workflows.
- A successful closing run remains live PR candidate evidence, not proof of a
  CI Playbook entry.
- Post-merge reconciliation checks recording completeness without curating or
  deduplicating the Playbook.
