# Independent review inspection

<!-- ips-role: procedure -->
<!-- ips-rule: review-inspection -->

## Read when

Read this file only after review setup proves the exact isolated clone.

## Procedure

1. Obtain the canonical GitHub PR patch and complete paginated file inventory
   without depending on the local commit graph.
2. In the isolated clone, obtain the exact endpoint inventory with
   `git diff --name-status <expected-base-sha> <expected-head-sha>` and the
   endpoint patch with
   `git diff --binary <expected-base-sha> <expected-head-sha> --`. These
   two-endpoint comparisons do not require a merge base; never rely on a
   three-dot comparison as the only complete-diff proof.
3. Normalize paths and change statuses.
   Require the GitHub and exact endpoint inventories to agree on the complete
   focused file set before judging the diff. An unexplained file or status
   mismatch is a blocking limitation and returns through live-state recovery.
4. Judge behavior against focused scope, non-targets, failure model,
   acceptance criteria, relevant accepted design, tests, and public safety.
5. Before running verification, conduct a bounded pre-mortem of the exact
   candidate. Assume it has been merged and caused a material failure within
   the focused scope and accepted design. Identify the most plausible trigger,
   propagation, material impact, detection, and recovery paths, then inspect
   the exact diff and evidence against them.
6. Treat those failure paths as inspection hypotheses, not findings. Promote a
   scenario to an actionable finding only when concrete evidence from the
   current candidate proves a defect in the accepted scope. Do not turn an
   unevidenced hypothesis into speculative expansion or a new requirement.
7. For public guidance or evidence, read
   [public safety](../references/public-safety.md), then return here.
8. Run the smallest relevant non-Docker static verification. Do not start or
   mutate Docker Desktop.
9. Require PR evidence to justify selected, executed, carried, and skipped
   groups with both N/NN counts. Reject a carry without successful unaffected
   evidence. Affected omissions remain skipped without evidence and require
   focused rationale plus an exact-head trailer.
10. Apply the same evidence rule to Docker-backed groups without running them
   locally.
11. Read the exact-head Actions result and limitations.
12. Only when the exact candidate claims a qualified Markdown-only skip, read
    the [Markdown-only exception](../ci/exceptions/markdown-only.md#independent-review),
    return here, and verify every required condition.
13. Classify actionable findings by severity and cite exact file, line, or
    behavioral evidence. Do not request speculative expansion.
14. For re-review, verify every prior finding against the new code and still
    inspect the complete current PR.
15. Separately classify every evidenced reusable process or review candidate
    discovered in this review cycle. Split compound observations into atomic
    root-cause candidates, preserve their stable discovery order, and retain
    every candidate for the verdict. Use `none` only when no reusable candidate
    was discovered. A candidate becomes an actionable finding only when it
    also exposes a defect in the current accepted scope.

## Verdict guard

Do not approve a moved head, stale description, mislabelled older evidence,
unavailable required proof outside the explicit exception, prohibited review
mutation, unresolved actionable finding, or an omitted reusable-governance
candidate classification.

## Next

When inspection is complete, open [review verdict](verdict.md).
