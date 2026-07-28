# Staged pre-commit hardening

<!-- ips-role: procedure -->
<!-- ips-rule: ci-preflight -->

## Read when

Read this file only after implementation and test intent are complete and the
exact candidate is staged without a commit.

## Procedure

1. Inspect the complete intended diff and staged file list.
2. Run `python scripts/verify.py --plan --staged`.
3. Record both N/NN counts and the selected, executed, carried, and skipped
   groups.
4. If changed boundaries match reusable runner knowledge, use the
   [knowledge selector](../knowledge/selector.md), read one matching leaf at a time,
   return here, and apply only relevant rules.
5. Correct portability, dependency, real-service, recovery, evidence, or
   teardown risks without weakening intended proof.
6. Rerun required verification after every correction.
7. Inspect and stage the corrected candidate again. Commit only the verified
   staged state.

The first staging is a review snapshot, not permission to commit stale index
content after later edits.

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
- Reverify and restage stale content.
- Return a material correction to the caller for focus selection.
- When a changed boundary cannot map to accepted proof, select conservative
  full verification and record the missing mapping for a focused knowledge
  correction.

## Next

- Missing or mismatched local tools: read [local rehearsal](local-rehearsal.md)
  and return here.
- Failed Actions after publication: read
  [failed-run triage](failure-triage.md).
- Hardened verified staged state: return to the calling implementation or
  publication workflow.
