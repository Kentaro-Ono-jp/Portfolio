# GitHub Actions workflows

GitHub Actions will be the authoritative build and runtime verification
environment for this portfolio.

Use the thin [CI router](../../ips-microkernel/ci/router.md) after a complete
implementation and its tests have been staged without a commit. It selects
staged preflight, local rehearsal, an explicit exception, failed-run triage,
post-merge reconciliation, or one relevant knowledge leaf without loading them
together.

A machine-qualified Markdown-only PR may skip Actions only through the
router's separate exception. At merge, its explicit squash-message boundary
makes the Markdown-only `main` commit skip Actions too. Neither absent run is
passing evidence.

`verify.yml` runs the repository-owned `scripts/verify.py` entrypoint on pull
requests, `main`, and manual dispatch. It proves the canonical contracts,
generated types, documentation links, static analysis, pinned API/ML dependency
audits, API/dispatcher/ML images, deterministic model generation, real
PostgreSQL/MinIO/RabbitMQ behavior, CPU PyTorch inference, pinned Dex OIDC
validation, populated principal migration, publisher
confirmation, stable ML failure, at-least-once duplicate handling, restart
recovery, complete nine-service readiness, and the Playwright
browser-to-ML-to-browser approval, correction, audit, security-negative,
completed, and failed paths from a clean GitHub-hosted runner.

After successful canonical verification, a separate least-privilege job
publishes each selected Web, API, and ML coverage report to Codecov under its
own carry-forward flag. The publication job receives GitHub OIDC authority but
does not execute repository tests, requires no stored Codecov token, and fails
the workflow when an expected report or upload is unavailable.

A PR carries only unaffected evidence from an exact successful baseline. When
that baseline is unavailable, a repository-owner PR falls back to a cold full
selection with no carried evidence; an external PR stops before dependency or
Docker setup.

When verification fails, sanitized Compose state, timestamped logs, ML
readiness, JUnit, model/runtime proof, and branch-aware coverage evidence are
uploaded from `artifacts/verification/`. Playwright trace, screenshot, video,
and HTML containers remain in the non-uploaded
`artifacts/private-verification/` boundary. Upload proceeds only after
credential patterns plus registered submitted-source, submitted-private-data,
and private-profile canaries are removed from ordinary files and ZIP members,
the public root is re-scanned, and no private browser container is present.
Leakage-scan or artifact-upload failure cannot suppress the unconditional final
step that removes only the
`reactorfront-portfolio` project and its three ephemeral runner volumes.

AI-agent local work uses the static verifier and does not start Docker Desktop.
The Docker-backed complete-slice proof is owned by this workflow.
