# End-to-end tests

This directory contains tests that verify complete user-visible workflows
against the assembled system.

Playwright drives the complete authenticated review workflow using generated,
repository-owned single-page PDFs. It verifies real OIDC sign-in, private
source integrity, an approved invoice, an intentionally invoice-biased
synthetic fixture corrected to its documented `report` ground truth, ordered
audit history, identical idempotent replay, stale-precondition and CSRF
rejection, sign-out denial, request/response correlation identity, an
`INVALID_PDF` terminal path, and local non-PDF rejection against the assembled
nine-service Compose system. The correction fixture proves workflow behavior,
not production model quality.

The GitHub Actions runtime installs the pinned Chromium build and runs
`pnpm e2e:test`. Failure traces, screenshots, video, HTML, and JUnit output are
written below `artifacts/verification/`; the canonical verifier adds concise
nine-service readiness, review invariants, and three-path cross-service
correlation proof. Before failure artifacts are uploaded, a credential-leakage
sanitizer redacts and re-scans ordinary files and ZIP members. AI-agent local verification
type-checks and formats this suite without starting Docker or a browser
workflow.
