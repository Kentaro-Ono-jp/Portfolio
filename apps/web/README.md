# Web application boundary

## Responsibility

This Next.js application owns the authenticated browser experience: completing
the OIDC Authorization Code flow with PKCE, selecting a supported document,
submitting it, following API-owned processing state, retrieving the verified
source, presenting the completed or failed terminal result, committing one
ETag- and idempotency-guarded human decision, and displaying ordered audit
history.

The browser calls only same-origin route handlers under `/api/documents`. Those
server-only handlers require an opaque Web session, forward its access token to
the API base URL in `PORTFOLIO_API_BASE_URL`, preserve canonical problem
responses, and prevent tokens and the private upstream address from entering
the client bundle.

In the AWS runtime, `PORTFOLIO_WEB_OIDC_RESOURCE` adds Cognito resource binding
to the Authorization Code/PKCE request. The resulting access token carries the
exact API audience that the FastAPI boundary validates; local Dex mode leaves
the optional resource parameter unset.

## Boundary rules

- Consume backend capabilities only through the canonical OpenAPI contract.
- Do not access PostgreSQL, RabbitMQ, object storage, or ML code directly.
- Do not import internal source from `apps/api` or `apps/ml`.
- Use generated TypeScript types from `@reactorfront/contracts`, then validate
  every runtime response with local Zod schemas at the HTTP boundary.
- Keep upload constraints aligned with the API: one PDF at most 5 MiB.
- Stop polling when the document reaches `completed` or `failed`.
- Keep access, refresh, and ID tokens only in the bounded server-side session
  store. The browser receives only an opaque `HttpOnly`, `SameSite=Lax` cookie.
- Require CSRF verification for state-changing same-origin routes.
- Derive the callback URI from the configured public base URL, validate OIDC
  discovery, explicit authorization and backchannel endpoints, and callback
  state/nonce/PKCE, and allow plaintext transport only for the explicit
  loopback Compose profile.
- Stream a source PDF to the browser only after the API verifies its owner,
  metadata, size, and SHA-256 digest.
- Preserve the API review entity tag and require CSRF, `If-Match`, and an
  idempotency key for the one terminal review mutation.
- Validate immutable machine evidence, terminal human-review state, and
  deterministically ordered audit events before rendering them.
- Admit strict measured runtime lineage and explicit `legacy-unmeasured`
  compatibility in shared response validators.
- Present a bounded evidence panel that keeps the per-document confidence score
  distinct from model-quality claims, shows exact measured dataset, pipeline,
  artifact, policy, and report identities, and never fabricates lineage for a
  legacy result.

## Implementation

- Next.js App Router with strict TypeScript and React
- Tailwind CSS for the visual system
- TanStack Query for mutations, polling, and server state
- Zod for server and browser response validation
- openid-client for OIDC Authorization Code, PKCE, callback, and refresh-token
  protocol handling
- Vitest and Testing Library for focused behavior tests
- A numeric non-root standalone Node.js container exposed on loopback by
  Compose

Browser-level Playwright coverage is owned by `tests/e2e` because sign-in and
document processing cross Web, identity, API, broker, ML, persistence, and
browser boundaries rather than belonging to Web internals.

## Configuration

`PORTFOLIO_API_BASE_URL`, `PORTFOLIO_WEB_PUBLIC_BASE_URL`, the explicit
OIDC issuer, authorization, discovery, token, and JWKS values, and
`PORTFOLIO_WEB_OIDC_CLIENT_ID` are required server settings. The optional
client secret enables a confidential client; the committed Compose fixture is
an intentionally public loopback-only client. Session absolute, inactivity,
transaction, refresh-leeway, scopes, and upstream-timeout settings have bounded
defaults documented in [`.env.example`](../../.env.example).

Production-shaped configuration requires HTTPS for the public Web URL and all
OIDC endpoints. The authorization endpoint may use Cognito's distinct domain
but must match discovery exactly. `PORTFOLIO_WEB_OIDC_ALLOW_INSECURE_LOOPBACK=true`
is accepted only when the public Web URL, issuer, and authorization endpoint
are HTTP loopback URLs. See the
[AWS runtime compatibility guide](../../AWS_RUNTIME_COMPATIBILITY.md).

Run the app from the repository root after installing the pinned workspace:

```console
pnpm --filter @reactorfront/web dev
```

The development server is available at `http://127.0.0.1:3000` by default;
configure that exact origin and callback URI in the selected identity client.
The Compose service is published at `http://127.0.0.1:53000` unless
`PORTFOLIO_WEB_PORT` overrides that host port.

## Verification

Focused checks are available from the repository root:

```console
pnpm --filter @reactorfront/web lint
pnpm --filter @reactorfront/web format:check
pnpm --filter @reactorfront/web typecheck
pnpm --filter @reactorfront/web test:coverage
pnpm --filter @reactorfront/web build
pnpm audit --prod --audit-level moderate
```

The canonical `python scripts/verify.py` entrypoint owns the combined static
and Compose proof. AI-agent local work uses `--static-only`; GitHub Actions
owns the Docker-backed Playwright proof.
