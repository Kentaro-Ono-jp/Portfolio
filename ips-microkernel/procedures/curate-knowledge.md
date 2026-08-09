# Knowledge curation workflow

<!-- ips-role: procedure -->
<!-- ips-rule: knowledge-curation -->

## Read when

Read this file when one or more atomic reusable governance candidates have
stable evidence, every associated actionable finding, if any, has complete
adjudication, and either every required correction has successful exact-head
proof or a complete exact-head `converge` checkpoint truthfully accepts the
unresolved corrections and known regression risk. Also read it for an
uncurated late candidate during post-merge reconciliation.

Do not enter this general curation role for Implementation Prune Stage A
occurrences, Stage B operational rules, or CI Playbook correction records.
ADR-0019 writes those after concrete corrections without Evidence admission,
proof status, promotion, or curation. A separately identified reusable
governance candidate may return here on its own evidence-bound route.

## Required inputs

- focused Issue and exact current lifecycle state;
- every source verdict URL, reviewed head, and numbered candidate;
- applicable adjudication checkpoints, aggregate decisions, and correction
  heads;
- current exact-head proof or exact merged-main proof for a late signal;
- any open `[Knowledge candidate]` Issue for the same selected signal key.

## Role boundary

The implementation agent may assume the **Knowledge Curator** role in the same
task, but it is a distinct runtime role. Freeze the candidate queue, source
evidence, current PR head or merge commit, correction chain, and proof while
this role is active.

Do not review, modify implementation or guidance, move the PR head, relabel a
verdict, or merge while curation is incomplete. The curator may append the
complete curation checkpoint to the focused Issue and create or link the one
deferred or follow-up Issue required by its disposition.

## Procedure

1. Use [live-state exact checks](../references/live-state.md), return here, and
   require every source head, verdict, adjudication, current head or merge
   commit, and proof to agree.
2. Expand every numbered candidate item from every verdict
   into the ordered candidate queue. Add distinct candidates proved by correction, recovery, evidence
   reconciliation, or cleanup. Split compound observations into atomic root
   causes, preserve stable source order, and deduplicate only identical stable
   evidence. Never stop ingestion after the first verdict item.
3. For each queued candidate, require stable evidence, complete disposition
   for every associated actionable finding, if any, and either successful proof
   of every required correction or a complete exact-head `converge` checkpoint
   that names unresolved corrections and known regression risk. A candidate
   with no associated actionable finding or required correction remains
   eligible; an unproved or stale candidate is not eligible for curation.
4. Separate CI runner and Actions signals to the [CI router](../ci/router.md).
   Do not route CI Playbook correction records here merely because they recur.
   Return material product, delivery, architecture, security, or actor-authority
   redefinition to [focus](focus.md). Continue here only for bounded reusable
   collaboration knowledge.
5. Use the
   [governance knowledge selector](../selectors/governance-knowledge.md), read
   exactly one selected canonical target, then return here.
6. Compare the atomic signal with the existing rule, executable guards, and any
   open `[Knowledge candidate]` Issue for the same signal key. Judge whether it
   changes future behavior enough to justify permanent context and maintenance
   cost. Critical or High product impact alone never forces promotion.
7. Assign exactly one disposition:
   - `discarded`: product-specific, one-off, obvious, or not worth permanent
     context;
   - `already-represented`: the selected rule or guard already owns it;
   - `promote-current-pr`: one bounded causal rule can enter the unmerged
     current focused PR;
   - `promote-follow-up`: the reusable rule is late, cross-boundary, or too
     broad for the current PR;
   - `deferred`: a named recurrence or additional-evidence trigger is required;
   - `unclassified`: no honest canonical target or disposition is available.
8. Before implementation, append one curation checkpoint to the focused Issue.
   This durable record occurs before any promotion mutation and contains the
   candidate, stable evidence, signal key, selected target or `none`,
   existing-guard comparison, context-cost judgment, exact source and current
   heads, proof, disposition, rationale, and next route.
9. Apply the disposition:
   - `discarded`: preserve the checkpoint as terminal recoverable evidence;
   - `already-represented`: link the exact accepted rule and guard;
   - `promote-current-pr`: return to
     [implement and verify](implement.md) with the one selected rule; after the
     head moves, require fresh exact-head proof and independent review;
   - `promote-follow-up`: create or link one accepted focused governance Issue
     and route its own independently reviewed PR without blocking the proved
     current merge;
   - `deferred` or `unclassified`: create or reuse one open GitHub Issue whose
     title begins `[Knowledge candidate]` and record the signal key, stable
     evidence, origin, disposition, and deterministic resurfacing trigger.
10. After one outcome, return to step 3 for the next queued candidate.
    Only after the queue is exhausted may the lifecycle proceed to re-review,
    merge, or post-merge reconciliation.

## Same-PR guards

- Same-PR promotion is preferred only before merge, for one causally related
  bounded rule with a known canonical home.
- The curation checkpoint precedes implementation mutation; the curator never
  implements its own decision while the role is active.
- Any promoted guidance or executable guard changes the candidate head and
  invalidates older exact-head proof and verdicts.
- The final changed head must pass required proof and independent exact-head
  review. A stale approval cannot authorize merge.
- Material product, delivery, architecture, security, or actor-authority
  change returns to focus instead of entering the current PR silently.

## Deferred recovery

- Search open `[Knowledge candidate]` Issues only after the selector identifies
  the current signal key; do not preload a global backlog.
- A matching recurrence or named trigger adds stable evidence to the existing
  Issue and re-enters curation.
- Promotion or terminal discard closes the candidate Issue with the exact
  focused Issue, PR, proof, and disposition.
- The originating feature Issue may remain closed; the live candidate Issue
  preserves recoverability.

## Recovery

- A moved or unproved head returns through live-state and CI recovery.
- An incomplete associated finding disposition or convergence checkpoint
  returns to adjudication.
- A selected rule that materially changes accepted scope returns to focus.
- A candidate with no canonical target remains `unclassified`; never copy it
  into a nearby rule.
- A post-merge candidate cannot use `promote-current-pr`.

## Return

Return the complete per-candidate checkpoints and any selected implementation,
follow-up, or deferred Issue route to the calling lifecycle.
