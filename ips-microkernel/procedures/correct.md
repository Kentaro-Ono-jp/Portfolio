# Review correction workflow

<!-- ips-role: procedure -->
<!-- ips-rule: correction-workflow -->

## Read when

Read this file when an independent exact-head verdict contains actionable
findings.

## Procedure

1. Require the verdict SHA to equal the reviewed PR head and current expected
   review head.
2. Judge each finding against accepted design, focused scope, and concrete
   evidence. Do not implement speculative expansion.
3. If the owner explicitly accepts named residual findings for this exact head
   and authorizes merge without correction, record the real verdict URL,
   residuals, exact head, required proof, and owner waiver in the PR
   checkpoint. Do not relabel the verdict. Route that checkpoint to
   [merge](merge.md).
4. Route a correction that materially changes scope or accepted design to
   [focus](focus.md) as a new slice decision.
5. For a non-material in-scope correction, return to
   [implement and verify](implement.md). Standing policy covers diagnosis,
   correction, verification, commit, push, PR-evidence update, Actions
   execution, and an unchanged-head rerun when appropriate.
6. After the corrected candidate is verified and staged, use
   [publish](publish.md) as a follow-up push.
7. Require the new exact head to pass or satisfy a qualified Markdown-only
   exception, then request re-review.

A verdict applies only to its exact reviewed head.

## Recovery

- Refresh an untrusted or mismatched verdict through live-state checks and
  request a new independent review of the exact head.
- Reject prohibited review mutation as evidence and preserve the canonical
  workspace.
- Route a finding that requires material scope or design change to focus.
- Correct an in-scope conflict with accepted design toward the accepted design,
  never by weakening it.

## Next

- Correction required: loop to [implement and verify](implement.md).
- Corrected push required: move to [publish](publish.md).
- New verdict: re-enter this workflow for findings or move an approved exact
  head to [merge](merge.md).
- Exact owner waiver recorded: move the reviewed head to [merge](merge.md).
