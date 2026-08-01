# Post-merge CI correction reconciliation

<!-- ips-role: procedure -->
<!-- ips-rule: ci-post-merge -->

## Read when

Read this file after every feature PR merge, once the exact merge commit's
automatic `push` workflow completes. This route checks correction-record
completeness; it does not prove, deduplicate, promote, or curate CI Playbook
entries.

## Procedure

1. Require the exact merge SHA and completed default-branch workflow.
2. Audit only that PR's exact-head failed runs and corrective commits.
3. For each concretely corrected CI failure, require that the correction commit
   included one CI Playbook entry in the selector-owned leaf after correction.
   Duplicate entries are valid and no Evidence or proof state is required.
4. Require Stage A as well when the CI failure exposed an implementation
   mistake. Do not read unrelated PR occurrence files.
5. Record one bounded outcome in the focused Issue:
   - `CI correction reconciliation: complete` with the PR's corrected-failure
     count and record paths; or
   - `CI correction reconciliation: no corrected CI failure` when none exists.
6. A missing immediate record is a focused correction gap. Do not reconstruct
   or deduplicate the Playbook from all repository history and do not create a
   reusable-knowledge promotion candidate.

## Guard outcome

- A failed or missing exact-merge workflow returns to CI triage and leaves
  affected completion evidence open.
- An incomplete correction chain remains an explicit evidence gap.
- A duplicate or unproved Playbook entry is not a reconciliation failure.
- A repository correction for a missing record uses its own ordinary focused
  lifecycle; no push is created merely to certify an existing record.

## Return

Return the bounded correction-record outcome to post-merge reconciliation.
Issue checklist updates and delivery evidence are handled separately.
