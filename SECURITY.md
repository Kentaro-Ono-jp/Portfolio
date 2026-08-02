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

The canonical supported flow uses repository-owned synthetic identities and
single-page PDFs inside ephemeral GitHub Actions infrastructure. It exercises
real OIDC Authorization Code flow with PKCE against the pinned Dex test
fixture, a server-owned Next.js session, independent API bearer-token
validation, owner-filtered private source access, one immutable human review
decision, and append-only product audit history.

The browser receives only an opaque `HttpOnly`, `SameSite=Lax` session cookie.
OAuth tokens remain server-side, and state-changing same-origin operations
require CSRF verification. The API validates token signature, algorithm,
issuer, audience, time bounds, trusted keys, capabilities, and target ownership
on every protected request. Source PDFs remain private and are returned only
after persisted metadata, size, media type, and SHA-256 verification.

The committed Dex client, identities, and local passwords are visibly
synthetic loopback fixtures. They do not authorize an external system. No
GitHub Secret, production credential, external identity account, or maintainer
session is required by canonical verification. End-user tokens, authorization
codes, session cookies, signing material, private profile values, source text,
and submitted private data are excluded from durable business state, broker
messages, ML tasks, logs, and public evidence. Failure artifacts pass a private-
content leakage gate before upload, and teardown targets only the
`reactorfront-portfolio` Compose project.

This repository is not a persistent hosted service and does not operate
production user accounts. Dex is test infrastructure, not a selected
production identity provider. Production TLS termination, shared durable
sessions, secrets management, account recovery, MFA, multi-tenancy, cloud IAM,
and operational monitoring remain outside the completed slice. Supported
documents are bounded to one text-bearing PDF page of at most 5 MiB; scanned-
document OCR, multi-page processing, image upload, and production model-quality
or calibrated-confidence claims are also outside scope.

The complete implemented trust boundary and limitations are documented in
[`ips-microkernel/architecture/index.md`](ips-microkernel/architecture/index.md).

Public source does not make third-party systems or accounts valid test targets.
Do not probe infrastructure, identities, or services that are not owned by this
repository.
