# Failed-run triage and promotion

<!-- docforai-role: procedure -->
<!-- docforai-rule: ci-failure-triage -->

## Read when

Read this file only after an exact-head GitHub Actions run fails.

## Procedure

1. Pin the exact PR head and failed run.
2. Read the failing step, retained artifacts, and first causal service error
   before reacting to teardown noise.
3. Classify the signal as product semantics, dependency or image parity,
   invocation portability, persistence, state isolation, messaging, browser,
   readiness or recovery, or evidence and cleanup.
4. Use the [knowledge index](knowledge/README.md) and read only the matching
   leaf. Return here after comparing its known signal and durable guard.
5. Reproduce only through safe non-Docker local checks or GitHub Actions. Never
   start local Docker because Actions failed.
6. Fix the root cause and add the smallest executable regression protection.
7. Run allowed canonical verification, push the corrected head, and require
   its exact workflow result.
8. Promote only a new reusable decision rule. Update one canonical knowledge
   leaf or add one routed leaf; link stable evidence without copying raw logs
   or preserving a one-off workaround.

Do not add compatibility flags merely to make a pinned service accept obsolete
behavior. Remove unused topology or correct the application contract. Do not
replace bounded readiness polling with an unexplained fixed sleep.

## Recovery

- Refresh a moved head and re-pin the exact failed run.
- Rerun an unchanged exact head once when causal evidence was unavailable.
- Route material scope or design change to [focus](../workflows/focus.md).
- Move unsafe or environment-dependent reproduction to GitHub Actions.
- Reject a workaround that weakens accepted proof and continue root-cause
  analysis from the last exact checkpoint.

## Next

- Corrected implementation returns to its implementation and publication
  workflows.
- A successful closing run remains live PR evidence.
- Reusable knowledge is reconciled again after merge.
