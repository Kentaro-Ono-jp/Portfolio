# ADR-0007: Define the authentication, session, and API authorization boundary

- Status: Accepted
- Date: 2026-07-20
- Related decisions:
  - [ADR-0001: Adopt a modular monorepo](0001-modular-monorepo.md)
  - [ADR-0002: Target an AI-enabled document intelligence platform](0002-target-document-intelligence-platform.md)
  - [ADR-0003: Adopt the initial technology stack](0003-initial-technology-stack.md)
  - [ADR-0004: Keep state ownership in the API and use a transactional outbox](0004-api-state-ownership-and-transactional-outbox.md)

## Context

The completed first vertical slice deliberately exposes an anonymous,
loopback-only document-classification flow. The browser talks to same-origin
Next.js route handlers, those handlers proxy the canonical API, and the API
owns document and processing state. The public OpenAPI contract currently has
no security requirement.

The proposed next slice adds human review of a machine result. A reviewer must
be able to view the source document, approve or correct the classification,
and leave a traceable audit record. Adding those capabilities without first
defining authentication, session, and authorization boundaries would expose
private source objects and state-changing review operations to any caller.
Retrofitting identity after more document and review data exists would also
make ownership, migration, audit, and contract decisions harder.

The boundary must preserve the existing deployable areas:

- `apps/web` owns the browser experience and same-origin server boundary.
- `apps/api` remains the sole owner of application state and authorization
  decisions.
- `apps/ml` remains independent of end-user identity and PostgreSQL.
- `packages/contracts` describes the public API without sharing private
  authentication implementation.

The design must work with deterministic GitHub Actions verification without a
maintainer account, committed credential, external interactive login, or
provider-specific private state. It must also leave a credible path to a
managed identity provider and AWS deployment without choosing either one
prematurely.

## Decision

### Identity protocol and provider boundary

Use OpenID Connect (OIDC) for end-user authentication and OAuth 2.0 access
tokens for API authorization. Use the Authorization Code flow with PKCE for
the browser-mediated sign-in. Redirect URIs are pre-registered and matched
exactly. The implicit flow and resource-owner password credentials grant are
not supported.

The authorization server is an external identity dependency, not a fourth
application-owned deployable area. Product code depends on standard issuer
metadata, authorization and token endpoints, JWKS, claims, and scopes rather
than a provider SDK or provider-specific user model. Selecting a production
identity vendor remains a deployment decision.

An ID token establishes the Web application's user session. An OAuth access
token authorizes calls to the API. The API does not accept an ID token as a
substitute for an access token.

### Web session boundary

The Next.js server boundary acts as the browser-facing confidential client and
backend-for-frontend:

- It owns sign-in initiation, callback validation, server-side token handling,
  session renewal, and sign-out.
- It uses transaction-specific `state`, `nonce`, and PKCE values and validates
  the issuer and callback response before creating a session.
- Access and refresh tokens remain server-side. They are not placed in browser
  JavaScript, client bundles, URLs, `localStorage`, or `sessionStorage`.
- The browser receives only a protected, `HttpOnly`, `SameSite` session cookie.
  The cookie is `Secure` outside an explicitly bounded loopback-development
  exception and has a bounded lifetime.
- State-changing same-origin requests require CSRF protection in addition to
  authentication. A session cookie alone is not authorization for a mutation.
- The existing same-origin route handlers attach the access token when calling
  the API. The browser continues not to know the private API base URL.

Client-visible authentication and session failures use stable, sanitized
responses. Tokens, authorization codes, cookie values, and raw provider
responses are never written to application logs or browser-visible errors.

### API resource-server boundary

The API is the authoritative resource server. It independently validates each
access token before trusting a request, even when the request arrived through
the Web application. Validation includes:

- a signature made with an explicitly allowed asymmetric algorithm and a
  trusted issuer key
- exact issuer and intended API audience
- expiration and not-before constraints with a bounded clock-skew allowance
- the token's authorization scopes or equivalent normalized permissions

Trusted signing keys are discovered through the configured issuer metadata and
JWKS, cached for a bounded period, and refreshed for legitimate key rotation.
The API fails closed when no trusted key can validate a token. Network failure
does not cause signature, issuer, audience, or time validation to be skipped.

Document and review operations require authentication by default in the
canonical OpenAPI contract. Process health and dependency-readiness endpoints
may remain unauthenticated for container orchestration, but they expose no
identity, token, document, or dependency-secret detail.

Missing or invalid credentials return a canonical `401` problem and the
appropriate bearer challenge. A valid principal without permission returns a
canonical `403` problem. Both preserve the existing correlation-identifier
contract without exposing token-validation internals.

### Authorization and actor identity

Authorization is deny by default and checked by the API for every protected
operation and target resource. The initial review slice may expose a small set
of explicit capabilities such as document submission, document read, review
write, and audit read. Possession or discovery of a document identifier never
grants access by itself.

The API derives the actor from the validated token. It never accepts a user,
tenant, role, issuer, or subject from a request body or an untrusted forwarding
header as proof of authority.

When application state needs a durable actor, the API maps the OIDC issuer and
subject pair to an API-owned principal identifier. The `(issuer, subject)` pair
is the stable external identity; email address, display name, and username are
not authorization keys and are not stable audit identities. Review decisions
and audit events store the API-owned principal reference, not an access token
or a copied token payload.

The proposed review slice may begin with one shared synthetic review space and
one reviewer capability set. Multi-tenancy, organization membership,
assignment queues, and administrative role management are separate product
decisions. Their absence does not permit protected endpoints to bypass the
principal and resource authorization checks.

### Token containment and downstream isolation

End-user tokens cross only the Web-to-API HTTP boundary. The API translates an
authorized request into API-owned actor and domain identifiers before writing
state or publishing work.

Access tokens, refresh tokens, ID tokens, authorization codes, session cookies,
and complete token claims are not stored in PostgreSQL or object storage and
are not placed in RabbitMQ messages, outbox payloads, ML task envelopes, audit
payloads, traces, metrics, or logs. The ML worker remains unaware of end-user
authentication and receives only the existing document, job, correlation,
object, and source-integrity identities.

### Source-document access

Source objects remain private. For the first authenticated review slice, the
API authorizes the document resource and streams the supported PDF through the
existing Web server boundary. The browser does not receive object-store
credentials or a durable public object URL.

Direct browser access through short-lived presigned URLs is deferred. If later
document size or measured transfer cost requires it, a separate decision must
define resource binding, expiration, revocation limits, response headers, and
leakage tests before bypassing the API streaming path.

### Configuration and deterministic verification

Issuer URLs, client identifiers, API audiences, redirect URIs, scopes, and
session settings are explicit server-side configuration. Production client
credentials and session secrets are never committed. Startup and readiness
must distinguish invalid configuration from a temporarily unavailable issuer
without exposing secret values.

Canonical verification uses a pinned OIDC-compatible test authorization server
or equivalent protocol-faithful test boundary with repository-owned synthetic
identities and ephemeral runtime signing material. It requires no GitHub
Secret or external user account. Browser and API tests prove at least:

- the real authorization-code, PKCE, callback, and session path
- unauthenticated rejection for every protected operation
- rejection of invalid signature, issuer, audience, expiry, and permission
- CSRF rejection for an otherwise authenticated state-changing request
- authorized source-document access and review mutation
- separation between `401` authentication and `403` authorization failures
- absence of tokens and private claims from logs, events, artifacts, and
  persisted application state
- preservation of the existing API, outbox, result-consumer, ML, and browser
  recovery evidence

The test authorization server is test infrastructure. It does not become the
product's user database or a source-code dependency shared across the Web and
API implementations.

## Consequences

### Positive

- Authentication is based on current interoperable standards rather than a
  portfolio-specific password system.
- The browser, Web server, API, and ML worker have explicit trust boundaries.
- The API remains authoritative even if a Web route or client is bypassed.
- Stable issuer-and-subject identity supports review and audit records without
  treating mutable profile claims as keys.
- Machine-processing events remain free of credentials and provider coupling.
- A deterministic local issuer can prove the real protocol without requiring
  public hosting or maintainer secrets.
- A managed identity provider can replace the test issuer without changing the
  product domain or ML contracts.

### Costs

- The Web gains security-sensitive session, callback, renewal, logout, and
  CSRF responsibilities.
- The API gains token validation, key rotation, permission mapping, and
  principal-resolution responsibilities.
- Canonical Compose and browser verification gain identity infrastructure and
  additional failure modes.
- Local development requires an explicit authenticated path instead of direct
  anonymous document requests.
- Provider metadata and key availability require bounded caching, readiness,
  rotation, and outage tests.

## Rejected alternatives

- Build and store first-party user passwords in the API solely for this
  portfolio.
- Use the OAuth resource-owner password credentials grant.
- Use the implicit flow or expose access tokens in browser URLs or storage.
- Trust Web-only authentication while leaving the API endpoints anonymous.
- Accept an OIDC ID token as the API's OAuth access token.
- Authenticate API requests with one shared static API key.
- Trust actor, role, tenant, or ownership values supplied by the browser.
- Pass end-user tokens through RabbitMQ or into the ML worker.
- Couple the product domain directly to one identity vendor's SDK, user ID, or
  role format.
- Publish source documents from a public object-store bucket.

## Deferred decisions

- production identity provider and provider-specific deployment adapter
- concrete Web session library and token-cache implementation
- multifactor authentication, passkeys, account recovery, invitation, and user
  administration
- multi-tenant workspace, membership, assignment, and administrative policies
- native or third-party non-browser clients
- sender-constrained tokens through DPoP or mutual TLS
- service-to-service identity between the API process roles, broker, object
  store, and ML worker
- persistent public hosting, TLS termination, secrets management, and AWS IAM
  integration

## Revisit when

- a production identity provider or persistent deployment target is selected
- a second browser or non-browser client requires a different token-exchange
  or session model
- multi-tenant or resource-ownership rules exceed the initial reviewer
  capability model
- measured token replay risk justifies sender-constrained access tokens
- source-document size or transfer cost justifies carefully bounded presigned
  object access
- another deployable area needs end-user identity for a product requirement

## References

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0-18.html)
- [RFC 9700: Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html)
- [RFC 7636: Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636.html)
- [RFC 6750: OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html)
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
