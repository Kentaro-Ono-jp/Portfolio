# GitHub Actions workflows

GitHub Actions will be the authoritative build and runtime verification
environment for this portfolio.

Use the [CI playbook](CI_PLAYBOOK.md) only after a complete implementation and
its tests have been staged without a commit. It also governs the required
post-merge CI-knowledge reconciliation for every feature PR.

An owner-approved Markdown-only PR may skip Actions from its initial head under
the playbook's evidence boundary. At merge, use its explicit squash-message
boundary so the Markdown-only `main` commit also skips Actions. Neither the PR
head nor merged-main run is required for this narrow exception.

`verify.yml` runs the repository-owned `scripts/verify.py` entrypoint on pull
requests, `main`, and manual dispatch. It proves the canonical contracts,
generated types, documentation links, static analysis, pinned API/ML dependency
audits, API/dispatcher/ML images, deterministic model generation, real
PostgreSQL/MinIO/RabbitMQ behavior, CPU PyTorch inference, publisher
confirmation, stable ML failure, at-least-once duplicate handling, restart
recovery, complete eight-service readiness, and the Playwright
browser-to-ML-to-browser completed and failed paths from a clean GitHub-hosted
runner.

A PR carries only unaffected evidence from an exact successful baseline. When
that baseline is unavailable, a repository-owner PR falls back to a cold full
selection with no carried evidence; an external PR stops before dependency or
Docker setup.

When verification fails, sanitized Compose state, timestamped logs, ML
readiness, Playwright trace/screenshot/video/report output, JUnit,
model/runtime proof, and branch-aware coverage evidence are uploaded as a
retained artifact. Artifact-upload failure cannot suppress the unconditional
final step that removes only the
`reactorfront-portfolio` project and its three ephemeral runner volumes.

AI-agent local work uses the static verifier and does not start Docker Desktop.
The Docker-backed complete-slice proof is owned by this workflow.
