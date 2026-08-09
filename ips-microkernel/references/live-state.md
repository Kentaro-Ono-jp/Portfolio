# Live-state and discrepancy reference

<!-- ips-role: reference -->
<!-- ips-rule: bounded-live-state -->

## Read when

Read this file before an exact durable mutation or when local and live state is
dirty, missing, stale, contradictory, unavailable, or outside the actor model.

## Bounded orientation

1. Run `git status --short --branch` in the canonical workspace.
2. Read the governing delivery specification's tracking Issue and only the
   focused Issue, PR, verdict, and workflow evidence needed for the request.
3. Compare relevant local and remote heads before branching, pushing, merging,
   reconciling evidence, or deleting durable data.
4. Broaden the audit only after a concrete discrepancy.

Do not enumerate every branch, Issue, comment, workflow, history entry, or file
solely to detect an unknown writer while the trusted baseline is consistent.

## Exact mutation boundaries

| Boundary | Required exact check |
|---|---|
| Branch | Clean workspace, fetched `origin/main`, and intended base SHA |
| Push | Intended diff, local branch, remote branch, and full head SHA |
| Verdict reliance | Verdict SHA, current PR head, relevant Actions conclusion, and finding evidence |
| Adjudication | Verdict SHA and URL, current PR head, complete finding inventory, ordered correction-chain identity, focused-Issue checkpoint, aggregate decision, and unchanged candidate |
| Knowledge curation | Candidate source and ordinal, verdict and adjudication URLs, correction and current heads, required proof, selected signal key, focused-Issue checkpoint, and frozen queue |
| Merge | Reviewed head; `Approved`, complete zero-required `converge`, required-corrections-retained `converge`, or exact owner waiver over `continue-correction`; complete curation for every reusable candidate; passing proof or qualified exception; and established merge method |
| Checklist update | Exact merge commit, successful main run or qualified exception, and criterion-by-criterion proof or named owner acceptance |
| Cleanup | Identified task-owned target, exact tip or root, and recoverable scope |

## Deterministic recovery

1. Refresh the smallest affected local and live boundary once.
2. Re-evaluate the ordered route against the refreshed exact state.
3. Reverify and restage a stale local index; never overwrite unrelated files.
4. For unrelated dirty state, preserve it and use an isolated clean worktree
   when the focused mutation can continue independently.
5. For a moved head, adopt the refreshed exact head only when its ancestry and
   diff remain compatible with the accepted slice, then repeat applicable
   verification and review.
6. For an unknown writer or changed automation, inspect only its concrete
   mutation. Adopt compatible proved state; do not overwrite conflicting state.
7. Return any material effect on outcome, scope, non-targets, or accepted
   design to the caller for focus selection.
8. If recovery remains unsafe but does not change the slice, defer only the
   affected mutation and report the exact preserved checkpoint and limitation.

## GitHub unavailable

Use tracked sources for safe offline work only. Do not infer current PR, Issue,
check, or merge state from local memory. Continue safe local work and retry the
required live read before any remote mutation.

## Return

Return after the discrepancy is resolved, the exact boundary is proved, or the
unsafe side effect is explicitly deferred with its checkpoint preserved.
