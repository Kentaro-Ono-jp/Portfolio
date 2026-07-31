# Pre-CI / pre-push hardening

<!-- ips-role: procedure -->
<!-- ips-rule: ci-preflight -->

## Read when

Read this file only after first-pass Behavior and Proof implementation is
complete, verified, locally committed, and ready for an initial or follow-up
task-branch push. Past-mistake knowledge is not a first-pass design input.

## Procedure

1. Resolve the exact comparison endpoint: focused base to local `HEAD` for an
   initial push, or the expected current remote/PR head to local `HEAD` for a
   follow-up. Require the intended remote tip, a complete local commit, and a
   clean worktree and index.
2. Inspect the complete committed endpoint diff and run
   `python scripts/verify.py --plan --base <comparison-endpoint>`.
3. Record both N/NN counts and the selected, executed, carried, and skipped
   groups.
4. Use the [CI knowledge selector](../knowledge/selector.md) for each boundary
   triggered by the complete Proof delta. Read one leaf at a time, return here,
   and apply relevant proof-semantic and execution rules.
5. Use the [Behavior careless-mistake guide](../../knowledge/behavior.md) for
   each `pre-CI` entry triggered by the complete Behavior delta. Do not read its
   `pre-review` entries at this gate.
6. For every review or CI correction, make one explicit direct knowledge
   write-back decision before push:
   - Behavior lesson: strengthen or add one atomic entry in the Behavior guide
     with the correct phase;
   - Proof lesson: strengthen the matching CI leaf;
   - compound lesson: split it between the canonical homes;
   - admitted unowned Proof lesson: add one bounded CI leaf and selector route;
   - no reusable lesson: prepare `Knowledge write-back: none` plus concrete
     rationale for the PR correction evidence.
   There is no temporary intake or pending-candidate queue.
7. Correct every known failed check without weakening accepted behavior or
   proof. Run canonical verification, stage, and locally commit the complete
   correction and direct write-back.
8. Whenever local `HEAD` changes, restart at step 1. Never push a head that was
   not the exact clean head checked by the restarted gate.
9. Return the exact checked local SHA, comparison endpoint, verification plan,
   and knowledge write-back decision to publication.

## Selection and evidence lineage

- Carry only successful unaffected evidence.
- Missing baseline evidence forbids carried results. An owner-authored PR uses
  a cold full selection; an external PR replans from its trusted base before
  dependency setup.
- An intentionally omitted affected group is skipped without evidence and
  disclosed in the focused Issue, PR, and exact candidate's complete
  `Verification-Skip` trailer.
- Every follow-up head restates its complete current skipped set. A later head
  cannot silently drop an inherited gap that its delta did not execute. The
  planner must reject a head whose trailer omits that gap.
- A current skip declaration cannot replace carried successful baseline
  evidence.
- Rename and copy detection must include both operations and unmodified copy
  sources, then select both paths.
- Docker-backed groups follow the same selection rules but run in GitHub
  Actions, never through local Docker.

The planner keeps baseline and current-head trust separate:

- a successful PR base or main baseline is trusted regardless of current PR
  author
- an owner PR may use its previous successful head incrementally
- an external PR replans from its trusted base, ignores external head trailers,
  and executes inherited gaps plus dependent groups
- a tree-identical owner merge carries exact-head evidence only after reading
  both owner PR-head and merge-commit trailers and applying the same lineage
  check as a changed tree
- other merges replan from the successful main baseline

## Standing lifecycle policy

Within an accepted focused Issue, non-material corrections, verification,
commit, push, Draft PR evidence updates, Actions execution, and unchanged-head
reruns continue without a confirmation pause. Ready, merge, evidence, and
cleanup use their own exact guards. Material scope or design change returns to
focus. Local Docker always falls back to Actions.

## Recovery

- Replan an untrusted baseline from the nearest trusted successful base.
- Add an undisclosed affected omission to the selected set or record it as an
  explicit evidence gap.
- Reverify, restage, and commit stale content, then restart Gate A.
- Return a material correction to the caller for focus selection.
- When a changed boundary cannot map to accepted proof, select conservative
  full verification and record the missing mapping for a focused knowledge
  correction.

## Next

- Missing or mismatched local tools: read [local rehearsal](local-rehearsal.md)
  and return here.
- Failed Actions after publication: read
  [failed-run triage](failure-triage.md).
- Hardened exact committed state: return to publication for push and read-back.
