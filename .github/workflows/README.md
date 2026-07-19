# GitHub Actions workflows

GitHub Actions will be the authoritative build and runtime verification
environment for this portfolio.

`verify.yml` runs the repository-owned `scripts/verify.py` entrypoint on pull
requests, `main`, and manual dispatch. It proves the canonical contracts,
generated types, documentation links, static analysis, API and dispatcher
images, real PostgreSQL/MinIO/RabbitMQ behavior, publisher confirmation,
at-least-once duplicate handling, and restart recovery from a clean
GitHub-hosted runner.

When verification fails, sanitized Compose state, timestamped logs, JUnit, and
coverage evidence are uploaded as a retained artifact. Artifact-upload failure
cannot suppress the unconditional final step that removes only the
`reactorfront-portfolio` project and its three ephemeral runner volumes.

The workflow will expand through later focused changes to build the Compose
project, wait for readiness, verify the business flow, preserve failure
evidence, and clean up only its ephemeral project resources.
