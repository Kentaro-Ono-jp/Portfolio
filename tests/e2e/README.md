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
`pnpm e2e:test`. Trace, screenshot, video, and HTML containers are written only
below non-uploaded `artifacts/private-verification/`; JUnit and the canonical
verifier's concise nine-service readiness, review invariants, and three-path
cross-service correlation proof use `artifacts/verification/`. Before browser
navigation, the test registers repository-owned submitted source/data and
private-profile canaries. Before public failure artifacts are uploaded, the
sanitizer redacts those exact canaries and credential patterns from ordinary
files and ZIP members, re-scans them, and rejects private browser containers in
the public root. AI-agent local verification type-checks and formats this suite
without starting Docker or a browser workflow.
