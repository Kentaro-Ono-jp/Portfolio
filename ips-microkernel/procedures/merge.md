# Ready and merge workflow

<!-- ips-role: procedure -->
<!-- ips-rule: merge-workflow -->

## Read when

Read this file after independent review approves the current exact head,
complete adjudication records zero required corrections, or the owner
explicitly accepts every named required correction for the exact reviewed
head, every reusable candidate has complete curation, and the required proof is
successful or machine-qualified.

## Procedure

1. Use [live-state exact checks](../references/live-state.md), return here, and
   require the live PR head, reviewed head, and intended merge target to agree.
2. Require exactly one valid outcome for that head:
   - an `Approved` verdict;
   - a complete focused-Issue adjudication that preserves the real RC URL,
     exact head, every finding and disposition, all accepted residuals, and
     records zero required corrections;
   - a durable owner waiver that preserves the real verdict URL and
     adjudication checkpoint, names every accepted required correction and
     residual, pins the exact head, and explicitly authorizes merge.
   Never infer or manufacture a disposition or waiver, and never relabel RC as
   Approved.
3. Require successful canonical exact-head GitHub Actions proof or the complete
   qualified Markdown-only exception. Canonical Actions runtime and coverage
   proof remains authoritative even when another provider reports a status.
4. Require one complete curation checkpoint for every reusable candidate in
   the applicable verdict and correction chain. Every
   `promote-current-pr` checkpoint must be implemented in this exact reviewed
   head. A pending, stale, or unimplemented promotion cannot reach merge.
5. Classify every exact-head check against live requirements before relying on
   GitHub's merge state:
   - read the complete exact-head Checks API inventory and combined commit
     status inventory, following pagination for both;
   - read classic branch-protection required status checks and every applicable
     active ruleset for the live PR base branch, following pagination and
     retaining each required context plus any pinned application or integration;
   - treat an explicit unprotected-branch response as no classic requirement
     only after the applicable-ruleset read also succeeds;
   - match required contexts to the exact-head inventory, including the pinned
     application or integration when the live rule specifies one;
   - when a required name exists as both a check run and a commit status,
     require both to pass; and
   - block when a required context is absent or pending, when a commit status
     is `error` or `failure`, or when a completed check conclusion is
     `action_required`, `cancelled`, `failure`, `stale`, or `timed_out`.

   For this guard, GitHub's passing check conclusions are `success`, `skipped`,
   and `neutral`; a passing commit status is `success`.

   `UNSTABLE`, `mergeable`, a check name, and a provider name are not evidence
   of requiredness. An unavailable, permission-denied, incomplete,
   contradictory, or unsupported protection/ruleset response is missing live
   evidence and blocks merge through recovery.
6. A terminally failing non-required external check may pass this guard only
   with one machine-qualified merge-evidence record per check containing:
   - the exact PR head SHA;
   - check kind and name, reported state or conclusion, and provider URL;
   - the successful live classic-protection and applicable-ruleset reads that
     prove the check is not required;
   - diagnostics as either `available` with its URL or `unavailable` with the
     provider limitation stated;
   - the successful canonical exact-head Actions run URL; and
   - each changed repository area covered by a canonical measured coverage
     gate, with its measured value, required threshold, and passing result.

   A non-required external failure remains recorded as a failure; never call it
   successful, dismiss it, lower a coverage threshold, or use this exception
   for a canonical coverage failure. Missing fields, uncovered changed areas,
   or contradictory values block merge through recovery. A successful
   non-required check needs no exception record. A pending or otherwise
   non-terminal external check cannot use this exception and blocks merge.
7. Pin merge to the reviewed head and use the repository's established merge
   method.
8. Change Draft to Ready and merge the pinned exact head without a separate
   confirmation pause.
9. For a Markdown-only squash, read the
   [exception's squash boundary](../ci/exceptions/markdown-only.md#squash-merge-boundary),
   return here, and supply the explicit subject and body it requires.
10. Record the exact merge commit. Do not reconcile checklists or delete
   branches in this state.

## Recovery

- A moved head or superseded verdict returns to publication and exact-head
  review.
- An incomplete or stale finding disposition returns to
  [adjudication](adjudicate.md).
- Pending, stale, or unimplemented candidate curation returns to
  [knowledge curation](curate-knowledge.md).
- A waiver that omits the verdict, adjudication, required corrections,
  residuals, exact head, or explicit merge authorization returns to
  correction; do not broaden it by inference.
- Missing proof returns through the
  [CI router](../ci/router.md).
- A required-check failure, incomplete live requiredness inventory, missing
  non-required external-check evidence, or canonical coverage failure keeps the
  exact checkpoint unmerged and returns through live-state or CI recovery as
  applicable.
- A merge-method discrepancy uses live-state recovery and the repository's
  current established method; never guess or broaden the merge target.
- If exact merge preconditions remain unproved, defer the merge mutation and
  preserve the approved or owner-waived checkpoint without a confirmation
  pause.

## Next

After a successful merge, open [reconcile](reconcile.md).
