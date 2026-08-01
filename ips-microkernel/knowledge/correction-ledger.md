# Stage A implementation-correction ledger contract

<!-- ips-role: knowledge -->
<!-- ips-rule: implementation-correction-ledger -->

## Read when

Read this contract only after correcting an implementation mistake in an
existing PR, whether surfaced during implementation, exact-head CI, Stage B,
or adjudicated review correction. Do not read it during first-pass
implementation, publication Gate A, pre-push hardening, CI Playbook selection,
or verification planning. Do not enumerate or read earlier PR record files.

## Record location

Append the occurrence to `knowledge/corrections/pr-NNNN.md`, using the current
four-digit PR number. Open only that current PR file. Create it when the PR has
no record file yet.

Record files are data, not routed guidance. They carry no `ips-role` or
`ips-rule` marker and are never linked into startup or pre-CI routes.

## Occurrence contract

Each `### Occurrence N` block contains exactly these fields:

- **PR:** the public `PR #NN` identifier;
- **Mistake:** the observed implementation mistake;
- **Correction:** the concrete change applied.

The required field order is PR, Mistake, Correction.

Append one block for every correction occurrence. Preserve repeated Mistake
and Correction text as separate occurrences; never merge, deduplicate,
rewrite, or delete an earlier occurrence merely because the same mistake
recurs.

Do not add `Evidence`, `Proof`, `Status`, or a permanence claim. The occurrence
records what was changed; it does not claim that the correction is proved,
merged, reusable, or permanently correct.

## Timing and publication

Write the occurrence immediately after the correction exists and before the
next ordinary candidate commit. Do not wait for merge, exact-head CI,
independent review, or a dedicated proof push.

The record travels with the same next ordinary push as the corrected
candidate. Never create a knowledge-only push or CI run to prove a Stage A
occurrence. Normal exact-head proof still applies to the complete candidate
that will merge.

## Return

Return to the routed correction or failed-run procedure after appending the
current PR occurrence. Do not inspect sibling record files.
