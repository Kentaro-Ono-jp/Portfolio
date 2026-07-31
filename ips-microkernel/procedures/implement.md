# Implement and verify workflow

<!-- ips-role: procedure -->
<!-- ips-rule: implementation-workflow -->

## Read when

Read this file when an accepted focused Issue and exact branch exist, but the
complete intended candidate is not yet staged and hardened.

## Procedure

1. Change only files required by the accepted slice and preserve unrelated
   work.
2. Keep observable behavior aligned with accepted design and the focused
   Issue. Apply one completed `promote-current-pr` checkpoint only at its
   selected canonical target. Return to [focus](focus.md) before a material
   expansion.
3. Use `python scripts/verify.py`; do not create a competing root verifier.
4. Select the smallest sufficient verification groups from the staged or
   review delta. Carry only successful unaffected evidence.
5. Record an intentionally omitted affected group as skipped without evidence,
   with focused-Issue rationale and the complete exact-head
   `Verification-Skip` trailer. Never relabel affected evidence as carried.
6. Run Docker-backed groups only in GitHub Actions. Never pause to request
   local Docker.
7. If a required local tool is missing, read
   [local tool authorization](../references/local-tools.md), then return here.
8. Inspect the complete intended diff. For public guidance or evidence, read
   [public safety](../references/public-safety.md), then return here.
9. Stage the exact complete candidate without committing.
10. Enter the [CI router](../ci/router.md) and select
    its staged pre-commit route.
11. Reverify and restage every correction. The index must equal the verified
    working tree before publication.

The first staging is a review snapshot. Later edits make that snapshot stale.

## Recovery

- Material scope or accepted-design change returns to [focus](focus.md).
- A local Docker requirement becomes an Actions-only proof requirement.
- A missing affected-group proof plan returns through CI preflight, which
  selects conservative proof or records an explicit evidence gap.
- Preserve unrelated changes in place and continue from an isolated clean
  worktree when the accepted slice can be implemented independently.

## Next

- Failed local or Actions proof returns through the CI router and then here
  after a concrete correction.
- A complete verified and hardened staged candidate opens
  [publish](publish.md).
