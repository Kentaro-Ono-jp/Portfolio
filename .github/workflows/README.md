# GitHub Actions workflows

GitHub Actions will be the authoritative build and runtime verification
environment for this portfolio.

`verify.yml` runs the repository-owned `scripts/verify.py` entrypoint on pull
requests, `main`, and manual dispatch. Its first increment proves the canonical
contracts, generated types, documentation links, and Compose definition from a
clean GitHub-hosted runner.

The workflow will expand through later focused changes to build the Compose
project, wait for readiness, verify the business flow, preserve failure
evidence, and clean up only its ephemeral project resources.
