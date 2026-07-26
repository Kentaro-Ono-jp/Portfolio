# Browser verification knowledge

<!-- docforai-role: knowledge -->
<!-- docforai-rule: ci-knowledge-browser -->

## Read when

Read this file when Playwright locators, accessible names, ARIA roles, or
framework-owned live regions are changed or ambiguous.

## Durable rule

Accessible-name substring matching can select both a landmark and a control
whose names overlap. Prefer exact accessible-name matching for reviewed labels.
Filter role locators by the expected user-visible message when framework live
regions share the intended role. Keep strict locator mode as the uniqueness
guard.

The canonical browser path remains
[`document-classification.spec.ts`](../../../../tests/e2e/document-classification.spec.ts).

## Return

Return to the calling CI procedure after locator uniqueness is proved. This
knowledge does not justify changing product wording solely to satisfy a test.
