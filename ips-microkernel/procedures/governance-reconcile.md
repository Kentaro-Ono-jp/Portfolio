# Governance knowledge reconciliation workflow

<!-- ips-role: procedure -->
<!-- ips-rule: governance-knowledge-reconciliation -->

## Read when

Read this file after every focused PR merge, once exact merged-main proof and
CI knowledge reconciliation are complete, or when a proved merge still has an
uncurated recovery, evidence, or cleanup candidate.

## Procedure

1. Require the exact merged head, merge commit, successful default-branch
   proof or qualified exception, focused Issue, PR, every verdict URL, and
   every pre-merge curation checkpoint.
2. Audit only this slice's review candidates, actionable findings, correction
   chain, bounded recovery, evidence reconciliation, cleanup outcomes, and
   completed curation dispositions.
3. Require every pre-merge atomic candidate to have exactly one complete
   curation checkpoint. Require every `promote-current-pr` outcome to be present
   in the Approved merged head with fresh exact-head proof and review.
4. Build an ordered queue from only distinct late recovery, evidence, cleanup,
   or post-merge signals that no pre-merge checkpoint owns. Preserve stable
   source order and deduplicate only identical stable evidence.
5. When the late queue is non-empty, open
   [knowledge curation](curate-knowledge.md) and return here with every outcome.
   A post-merge candidate cannot use `promote-current-pr`.
6. Return CI runner or Actions signals to the
   [CI router](../ci/router.md). Return material product, delivery,
   architecture, security, or actor-authority signals to
   [focus](focus.md).
7. Verify every `promote-follow-up` outcome links one bounded accepted focused
   governance Issue. Verify every `deferred` or `unclassified` outcome links
   one open `[Knowledge candidate]` Issue with its signal key, stable evidence,
   origin, disposition, and deterministic resurfacing trigger.
8. When the current focused governance PR already contains and proves the exact
   accepted update, do not create a recursive empty Issue.
9. Only after the complete pre-merge and late queues are exhausted, append one
   aggregate outcome to the focused Issue:
   - `Governance knowledge reconciliation: no new reusable finding` when every
     candidate is `discarded` or `already-represented`, or no candidate exists;
   - otherwise list each current-PR promotion, follow-up, deferred, and
     unclassified outcome with its stable checkpoint.
10. Return the exact aggregate, linked live-state Issues, and any bounded
    follow-up to post-merge reconciliation.

## Recovery

- A moved or unproved merge returns through live-state and CI recovery.
- A missing or duplicate pre-merge disposition returns to
  [knowledge curation](curate-knowledge.md); never infer it after merge.
- An unimplemented `promote-current-pr` outcome is a merge-evidence
  contradiction and cannot be relabelled as a follow-up silently.
- A late candidate that changes the completed slice materially returns to
  focus.
- A proposed rule without one canonical target remains `unclassified`.
- A deferred or follow-up Issue may remain open without weakening the current
  feature's proved completion evidence.
- Reconciliation never copies a candidate into a nearby rule or a tracked
  incident ledger.

## Return

Return to the post-merge reconciliation workflow with the exact focused-Issue
record, complete disposition inventory, linked live-state Issues, and any
required focused follow-up.
