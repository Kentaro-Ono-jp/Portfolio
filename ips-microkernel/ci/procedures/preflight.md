# Pre-push hardening (publication Gate A)

<!-- ips-role: procedure -->
<!-- ips-rule: ci-preflight -->

## Read when

Read this file only after the first complete Behavior and Proof implementation
is verified, locally committed, and ready for an initial or follow-up remote
push. Past Stage A occurrences and Stage B rules are not Gate A inputs.

## Procedure

1. Resolve the exact comparison endpoint: focused base to local `HEAD` for an
   initial push, or expected remote/PR head to local `HEAD` for a follow-up.
   Require the intended remote tip, complete local commit, and clean worktree
   and index.
2. Inspect the complete committed endpoint diff and run
   `python scripts/verify.py --plan --base <comparison-endpoint>`.
3. Record both N/NN counts and selected, executed, carried, and skipped groups.
4. Use the [CI Playbook selector](../knowledge/selector.md) for each boundary
   triggered by the complete Proof delta. Read one leaf at a time. Treat its
   duplicate and possibly unproved correction records as fallible operational
   history, compare them with accepted design and the current candidate, and
   repair applicable test/proof scripts before remote push.
5. Do not read prior Stage A occurrence files or the Stage B checklist in
   Gate A.
6. Correct every known failed check without weakening accepted Behavior or
   Proof. If that work corrects an implementation mistake in an existing PR,
   append the Stage A occurrence after the correction without reading sibling
   records.
7. Run canonical verification, stage, and locally commit the complete hardened
   candidate and any correction record.
8. Whenever local `HEAD` changes, restart at step 1. Never push a head that was
   not the exact clean head checked by the restarted Gate A.
9. Return the exact checked local SHA, comparison endpoint, verification plan,
   selected CI Playbook leaves, and applied test/proof repairs to publication.

Gate A is completed before `git push`. Never defer CI Playbook reading or
test/proof repair to the interval after remote push and before GitHub Actions.

## Selection and evidence lineage

- Carry only successful unaffected evidence.
- Missing baseline evidence forbids carried results. An owner-authored PR uses
  a cold full selection; an external PR replans from its trusted base before
  dependency setup.
- An intentionally omitted affected group is skipped without evidence and
  disclosed in the focused Issue, PR, and exact candidate's complete
  `Verification-Skip` trailer.
- Every follow-up head restates its complete current skipped set. A later head
  cannot silently drop an inherited gap that its delta did not execute.
- A current skip declaration cannot replace carried successful baseline
  evidence.
- Rename and copy detection must include both operations and unmodified copy
  sources, then select both paths.
- Docker-backed groups follow the same selection rules but run in GitHub
  Actions, never through local Docker.

The planner keeps baseline and current-head trust separate:

- a successful PR base or main baseline is trusted regardless of current PR
  author;
- an owner PR may use its previous successful head incrementally;
- an external PR replans from its trusted base, ignores external head trailers,
  and executes inherited gaps plus dependent groups;
- a tree-identical owner merge carries exact-head evidence only after reading
  owner PR-head and merge-commit trailers and applying the same lineage check
  as a changed tree; and
- other merges replan from the successful main baseline.

## Standing lifecycle policy

Within an accepted focused Issue, non-material corrections, verification,
commit, one ordinary push, Draft PR evidence updates, Actions execution, and
unchanged-head reruns continue without a confirmation pause. Recording Stage A,
Stage B, or CI Playbook content does not require a dedicated certification
push. Material scope or design change returns to focus. Local Docker always
falls back to Actions.

## Recovery

- Replan an untrusted baseline from the nearest trusted successful base.
- Add an undisclosed affected omission to the selected set or record it as an
  explicit evidence gap.
- Reverify, restage, and commit stale content, then restart Gate A.
- Return a material correction to the caller for focus selection.
- When a changed boundary cannot map to accepted proof, select conservative
  full verification and record the missing mapping for a focused correction.

## Next

- Missing or mismatched local tools: read [local rehearsal](local-rehearsal.md)
  and return here.
- Failed Actions after publication: read
  [failed-run triage](failure-triage.md).
- Hardened exact committed state: return to publication for remote push and
  read-back.
