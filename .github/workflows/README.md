# GitHub Actions workflows

GitHub Actions will be the authoritative build and runtime verification
environment for this portfolio.

Use the [CI playbook](CI_PLAYBOOK.md) only after a complete implementation and
its tests have been staged without a commit. It also governs the required
post-merge CI-knowledge reconciliation for every feature PR.

When a final docs-only correction skips its PR-head run, use the playbook's
explicit squash-message boundary so the new `main` commit remains free of skip
instructions and starts its mandatory automatic workflow.

`verify.yml` runs the repository-owned `scripts/verify.py` entrypoint on pull
requests, `main`, and manual dispatch. It proves the canonical contracts,
generated types, documentation links, static analysis, pinned API/ML dependency
audits, API/dispatcher/ML images, deterministic model generation, real
PostgreSQL/MinIO/RabbitMQ behavior, CPU PyTorch inference, publisher
confirmation, stable ML failure, at-least-once duplicate handling, and restart
recovery from a clean GitHub-hosted runner.

When verification fails, sanitized Compose state, timestamped logs, ML
readiness, JUnit, model/runtime proof, and branch-aware coverage evidence are
uploaded as a retained artifact. Artifact-upload failure cannot suppress the
unconditional final step that removes only the
`reactorfront-portfolio` project and its three ephemeral runner volumes.

The API result consumer, public result persistence, and Web flow remain for
later focused changes.
