# CI Playbook: browser corrections

<!-- ips-role: knowledge -->
<!-- ips-rule: ci-knowledge-browser -->

## Read when

Before remote push, read this leaf when the complete candidate changes
Playwright locators, accessible names, ARIA roles, or framework-owned live
regions.

## Correction records

### Make accessible locators unique

- **Origin:** Existing Playwright correction record for
  [`document-classification.spec.ts`](../../../tests/e2e/document-classification.spec.ts)
- **Trigger:** A landmark, control, or framework live region has an accessible
  name or role overlapping another element.
- **Mistake:** Accessible-name substring matching selected more than one
  element, or a broad role matched a framework-owned live region.
- **Correction:** Prefer exact accessible-name matching for reviewed labels,
  filter shared roles by the expected user-visible message, and retain strict
  locator mode as the uniqueness check. Do not change product wording solely
  to satisfy a locator.

## Return

Return to publication Gate A after repairing the triggered browser test
scripts.
