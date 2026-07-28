# Governance knowledge reconciliation workflow

<!-- ips-role: procedure -->
<!-- ips-rule: governance-knowledge-reconciliation -->

## Read when

Read this file after every focused PR merge, once exact merged-main proof and
CI knowledge reconciliation are complete, or when a proved merge still has a
recorded reusable process or review candidate.

## Procedure

1. Require the exact merged head, merge commit, successful default-branch
   proof or qualified exception, focused Issue, PR, and all verdict URLs.
2. Audit only this slice's review candidates, actionable findings, correction
   chain, bounded recovery, evidence reconciliation, and cleanup outcomes.
   Expand every numbered candidate item from every verdict into the
   ordered candidate queue. Then add other proved signals, split compound
   observations into atomic root-cause candidates, preserve stable source
   order, and deduplicate only identical stable evidence.
   Never stop ingestion after the first verdict item.
3. When the queue is empty, skip to step 9.
4. For each queued candidate, separate product defects and one-off observations
   from reusable process rules. A reviewer candidate is evidence to classify,
   not authority to mutate guidance.
5. Return CI runner or Actions signals to the
   [CI router](../ci/router.md). Return material
   product or structural signals to [focus](focus.md) and ADR or delivery
   change control.
6. For one reusable collaboration signal, use the
   [governance knowledge selector](../selectors/governance-knowledge.md), read the selected
   canonical target, then return here.
7. Compare the candidate with the existing rule and executable guards. Do not
   create a second canonical home or preserve raw review transcripts.
8. Record exactly one outcome for this candidate:
   - **none:** record
     it as product-specific, one-off, or already represented
   - **already satisfied:** link the current accepted focused governance PR
     and its proof; do not create a recursive empty Issue
   - **new reusable rule:** return to focus for owner selection, create or link
     one accepted focused governance Issue, and publish its independently
     reviewed update before the next feature increment
   - **unclassified:** record the exact candidate and gap without mutating a
     nearby rule
   After recording the outcome, return to step 4 for the next queued candidate.
9. Only after the queue is exhausted, write one aggregate outcome in the
   focused Issue. When no candidate produced an already-satisfied, new, or
   unclassified reusable rule, record
   `Governance knowledge reconciliation: no new reusable finding`.
10. Return every per-candidate outcome and its stable evidence to post-merge
    reconciliation.

## Recovery

- A moved or unproved merge returns through live-state and CI recovery.
- A candidate that changes the current slice materially returns to focus.
- A proposed rule without one canonical target remains unclassified.
- A reviewer omission does not authorize inference; use the verdict's exact
  field and other proved correction evidence.
- A follow-up governance Issue may remain linked without weakening or
  duplicating the current feature's proved completion evidence.

## Return

Return to the post-merge reconciliation workflow with the exact Issue record,
selected canonical target or `none`, and any required focused follow-up.
