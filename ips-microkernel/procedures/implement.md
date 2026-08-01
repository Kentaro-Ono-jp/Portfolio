# Implement and verify workflow

<!-- ips-role: procedure -->
<!-- ips-rule: implementation-workflow -->

## Read when

Read this file when an accepted focused Issue and exact branch exist, but the
complete intended Behavior and Proof implementation is not yet staged.

## Procedure

1. Build Behavior implementation from accepted design: the behavior, boundary,
   state transition, or collaboration workflow selected by the focused Issue.
2. Build Proof implementation from accepted design: tests, fixtures, runtime
   probes, verifier routing, and CI evidence that prove that behavior. Do not
   read prior Implementation Prune Stage A occurrence files, the Stage B
   checklist, or CI Playbook leaves while creating the first complete
   Behavior and Proof implementation.
3. Keep observable behavior aligned with accepted design and the focused
   Issue. Apply one completed `promote-current-pr` checkpoint only at its
   selected canonical target. Return to [focus](focus.md) before a material
   expansion.
4. Use `python scripts/verify.py`; do not create a competing root verifier.
5. Select the smallest sufficient verification groups from the staged or
   review delta. Carry only successful unaffected evidence.
6. Record an intentionally omitted affected group as skipped without evidence,
   with focused-Issue rationale and the complete exact-head
   `Verification-Skip` trailer. Never relabel affected evidence as carried.
7. Run Docker-backed groups only in GitHub Actions. Never pause to request
   local Docker.
8. If a required local tool is missing, read
   [local tool authorization](../references/local-tools.md), then return here.
9. Inspect the complete intended diff. For public guidance or evidence, read
   [public safety](../references/public-safety.md), then return here.
10. Stage the exact complete first-pass candidate without committing.
11. Reverify and restage every correction. The index must equal the verified
    working tree before publication.

After the complete implementation exists, publication Gate A selects relevant
CI Playbook leaves before remote push and uses their fallible correction
records to repair test/proof scripts. That pre-push use does not turn the
Playbook into first-pass design input.

The first staging is a review snapshot. Later edits make that snapshot stale.

## Recovery

- Material scope or accepted-design change returns to [focus](focus.md).
- A local Docker requirement becomes an Actions-only proof requirement.
- A missing affected-group proof plan returns through publication and Gate A,
  which selects conservative proof or records an explicit evidence gap.
- Preserve unrelated changes in place and continue from an isolated clean
  worktree when the accepted slice can be implemented independently.

## Next

- Failed local or Actions proof returns through the CI router and then here
  after a concrete correction.
- A complete verified staged candidate opens
  [publish](publish.md).
