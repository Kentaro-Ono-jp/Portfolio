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
   verdict. Route that checkpoint to
   [merge](merge.md).
4. Route a correction that materially changes scope or accepted design to
   [focus](focus.md) as a new slice decision.
5. For a non-material in-scope correction, return to
   [implement and verify](implement.md). Standing policy covers diagnosis,
   correction, verification, commit, push, PR-evidence update, Actions
   execution, and an unchanged-head rerun when appropriate.
6. After the complete correction exists, classify every reusable
   careless-mistake lesson. Write Behavior lessons directly to the
   [Behavior guide](../knowledge/behavior.md) in the correct phase and Proof
   lessons through the CI selector selected by publication's Gate A. Split
   compound lessons. If none qualifies, record `Knowledge write-back: none`
   with concrete rationale in PR correction evidence. Do not use a temporary
   intake queue.
7. After the corrected candidate and direct write-back are verified and staged,
   use [publish](publish.md) as a follow-up commit, Gate A, and push.
8. Require the new exact head to pass or satisfy a qualified Markdown-only
   exception, then complete Gate B before re-review. When the correction chain
   proves other reusable governance candidates outside this direct
   Behavior/Proof careless-mistake route, enter
   [knowledge curation](curate-knowledge.md) before re-review. Otherwise request
   re-review.

A verdict and its adjudication apply only to their exact reviewed head.

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
