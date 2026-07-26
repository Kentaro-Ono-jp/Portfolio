# Independent review inspection

<!-- docforai-role: procedure -->
<!-- docforai-rule: review-inspection -->

## Read when

Read this file only after review setup proves the exact isolated clone.

## Procedure

1. Inspect the complete PR diff against its stated base.
2. Judge behavior against focused scope, non-targets, failure model,
   acceptance criteria, relevant accepted design, tests, and public safety.
3. For public guidance or evidence, read
   [public safety](../reference/public-safety.md), then return here.
4. Run the smallest relevant non-Docker static verification. Do not start or
   mutate Docker Desktop.
5. Require PR evidence to justify selected, executed, carried, and skipped
   groups with both N/NN counts. Reject a carry without successful unaffected
   evidence. Affected omissions remain skipped without evidence and require
   focused rationale plus an exact-head trailer.
6. Apply the same evidence rule to Docker-backed groups without running them
   locally.
7. Read the exact-head Actions result and limitations.
8. Only when the exact candidate claims a qualified Markdown-only skip, read the
   [Markdown-only exception](../ci/markdown-only.md#independent-review), return
   here, and verify every required condition.
9. Classify actionable findings by severity and cite exact file, line, or
   behavioral evidence. Do not request speculative expansion.
10. For re-review, verify every prior finding against the new code and still
    inspect the complete current PR.
11. Separately classify every evidenced reusable process or review candidate
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
