# GitHub Actions workflows

GitHub Actions will be the authoritative build and runtime verification
environment for this portfolio.

No workflow exists yet because there are no executable services or checks.
The accepted first-slice specification requires `.github/workflows/verify.yml`
to build the Compose project, wait for readiness, run `scripts/verify.py`,
capture useful failure evidence, and clean up its ephemeral resources.
