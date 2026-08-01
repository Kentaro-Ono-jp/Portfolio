# Review correction workflow

<!-- ips-role: procedure -->
<!-- ips-rule: correction-workflow -->

## Read when

Read this file only after a complete exact-head adjudication records one or
more `required-correction` dispositions and no exact owner waiver accepts
them.

## Procedure

1. Require the adjudication's exact head, verdict SHA, reviewed PR head, and
   current expected review head to agree.
2. Implement only findings recorded as `required-correction`. Preserve
   `accepted-residual` and `non-material` dispositions without silently
   reopening or correcting them.
3. If the owner explicitly accepts every named required correction for this
   exact head and authorizes merge without correction, record the real verdict
   URL, adjudication checkpoint, accepted required corrections, exact head,
   required proof, and owner waiver in the PR checkpoint. Do not relabel the
   verdict. Route that checkpoint to [merge](merge.md).
4. Route a correction that materially changes scope or accepted design to
   [focus](focus.md) as a new slice decision.
5. For a non-material in-scope repository correction, return to
   [implement and verify](implement.md). Complete the concrete correction
   before any operational write-back.
6. Immediately after the implementation correction exists, open the
   [Stage A ledger contract](../knowledge/correction-ledger.md), append the
   current PR occurrence, and return here. Do not read sibling occurrence
   files or wait for proof.
7. After the adjudicated review correction exists, update the
   [Stage B checklist](../knowledge/behavior.md) only when the finding yields a
   cheap unambiguous machine-decidable pre-review check. Add detection, pass,
   and concrete repair text after correction; reuse one canonical rule instead
   of duplicating it. If no rule qualifies, write nothing and do not publish a
   `none` placeholder.
8. Verify and stage the complete correction plus its Stage A occurrence and
   any Stage B rule change. Use [publish](publish.md) for the follow-up Gate A.
   Gate A reads selected CI Playbook leaves and repairs test/proof scripts
   before one ordinary remote push.
9. Require the new exact head to pass or satisfy a qualified Markdown-only
   exception, then execute Stage B before re-review. Operational Stage A and
   Stage B write-back does not enter general Knowledge Curator curation.
   When the correction chain proves a separately reusable governance candidate,
   enter [knowledge curation](curate-knowledge.md) before re-review.

A verdict and its adjudication apply only to their exact reviewed head.

## HEAD-neutral correction

When the selected correction changes only PR title/body, review endpoints, or
another live surface that leaves the Git commit, branch ref, tree, and PR head
SHA unchanged:

1. correct the live surface first and read it back;
2. treat the corrected problem as meeting the Stage B recording requirement;
3. after correction, add or strengthen one deduplicated `neutral` Stage B rule
   with mechanical detection, exact pass condition, and concrete repair; and
4. rerun Stage B without requiring a push or CI run solely to certify the
   rule.

If repository persistence of that rule later moves `HEAD`, normal candidate
Gate A, exact-head CI, and independent review apply to the changed repository
candidate. They do not assign a proof status to the rule.

## Recovery

- Refresh an untrusted or mismatched verdict or adjudication through
  live-state checks and request a new independent review when the exact head
  cannot be preserved.
- Reject prohibited review mutation as evidence and preserve the canonical
  workspace.
- Route a finding that requires material scope or design change to focus.
- Correct an in-scope conflict with accepted design toward the accepted design,
  never by weakening it.

## Next

- Correction required: loop to [implement and verify](implement.md).
- Corrected push required: move to [publish](publish.md).
- Proved correction with pending reusable candidates: move to
  [knowledge curation](curate-knowledge.md).
- New `Changes requested` verdict: enter
  [adjudication](adjudicate.md) before any further correction.
- New Approved verdict: move the exact head to [merge](merge.md).
- Exact owner waiver recorded: move the reviewed head to [merge](merge.md).
