# End-to-end tests

This directory contains tests that verify complete user-visible workflows
against the assembled system.

Playwright drives the first complete browser workflow using a generated,
repository-owned single-page invoice PDF. It verifies the accepted upload,
asynchronous terminal `invoice` result, confidence, model version, request and
response correlation identity, an `INVALID_PDF` terminal path, and local
non-PDF rejection against the assembled eight-service Compose system.

The GitHub Actions runtime installs the pinned Chromium build and runs
`pnpm e2e:test`. Failure traces, screenshots, video, HTML, and JUnit output are
written below `artifacts/verification/`; the canonical verifier adds concise
eight-service readiness and cross-service correlation proof. AI-agent local
verification type-checks and formats this suite without starting Docker or a
browser workflow.
