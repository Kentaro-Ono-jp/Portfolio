# Governance knowledge reconciliation workflow

<!-- docforai-role: procedure -->
<!-- docforai-rule: governance-knowledge-reconciliation -->

## Read when

Read this file after every focused PR merge, once exact merged-main proof and
CI knowledge reconciliation are complete, or when a proved merge still has a
recorded reusable process or review candidate.

## Procedure

1. Require the exact merged head, merge commit, successful default-branch
   proof or qualified exception, focused Issue, PR, and all verdict URLs.
2. Audit only this slice's review candidates, actionable findings, correction
   chain, bounded recovery, evidence reconciliation, and cleanup outcomes.
3. Separate product defects and one-off observations from reusable process
   rules. A reviewer candidate is evidence to classify, not authority to
   mutate guidance.
4. Return CI runner or Actions signals to the
   [CI router](../../../.github/workflows/CI_PLAYBOOK.md). Return material
   product or structural signals to [focus](focus.md) and ADR or delivery
   change control.
5. For one reusable collaboration signal, use the
   [governance knowledge selector](../knowledge/README.md), read the selected
   canonical target, then return here.
6. Compare the candidate with the existing rule and executable guards. Do not
   create a second canonical home or preserve raw review transcripts.
7. Choose exactly one outcome:
   - **none:** record
     `Governance knowledge reconciliation: no new reusable finding` in the
     focused Issue
   - **already satisfied:** link the current accepted focused governance PR
     and its proof; do not create a recursive empty Issue
   - **new reusable rule:** return to focus for owner selection, create or link
     one accepted focused governance Issue, and publish its independently
     reviewed update before the next feature increment
   - **unclassified:** record the exact candidate and gap without mutating a
     nearby rule
8. Return the outcome and stable evidence to post-merge reconciliation.

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
