# Security Policy

## Supported version

This portfolio is an evolving pre-release system. Security fixes are applied to
the current `main` branch only; there are no supported release branches yet.

## Report a vulnerability privately

Do not open a public Issue, pull request, or discussion for a suspected
vulnerability. Use GitHub's private vulnerability reporting for this
repository. Include the affected commit, a minimal reproduction, the observed
impact, and any safe mitigation you have already tested.

Do not include real credentials, access tokens, private URLs, client data,
employer data, personal documents, or confidential identifiers in a report.
Replace sensitive values with synthetic examples. If a secret was exposed,
revoke or rotate it before continuing the report.

The maintainer will acknowledge a usable report, assess its scope, and keep the
reporter informed as a correction is prepared. This public portfolio does not
offer a paid bug-bounty program or a production-service response-time SLA.

## Security scope

The canonical supported flow uses repository-owned synthetic single-page PDFs
inside ephemeral GitHub Actions infrastructure. Persistent public hosting,
authentication, scanned-document OCR, multi-page processing, and production
model-quality claims are outside the completed first slice.

Public source does not make third-party systems or accounts valid test targets.
Do not probe infrastructure, identities, or services that are not owned by this
repository.
