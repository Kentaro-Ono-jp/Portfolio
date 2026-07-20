# Web application boundary

## Responsibility

This Next.js application owns the first-slice browser experience: selecting a
supported document, submitting it, following API-owned processing state, and
presenting the completed or failed terminal result.

The browser calls only same-origin route handlers under `/api/documents`. Those
server-only handlers forward to the API base URL in
`PORTFOLIO_API_BASE_URL`, preserve canonical problem responses, and prevent the
private upstream address from entering the client bundle.

## Boundary rules

- Consume backend capabilities only through the canonical OpenAPI contract.
- Do not access PostgreSQL, RabbitMQ, object storage, or ML code directly.
- Do not import internal source from `apps/api` or `apps/ml`.
- Use generated TypeScript types from `@reactorfront/contracts`, then validate
  every runtime response with local Zod schemas at the HTTP boundary.
- Keep upload constraints aligned with the API: one PDF at most 5 MiB.
- Stop polling when the document reaches `completed` or `failed`.

## Implementation

- Next.js App Router with strict TypeScript and React
- Tailwind CSS for the visual system
- TanStack Query for mutations, polling, and server state
- Zod for server and browser response validation
- Vitest and Testing Library for focused behavior tests
- A numeric non-root standalone Node.js container exposed on loopback by
  Compose

Authentication remains outside this slice. Browser-level Playwright coverage
is owned by `tests/e2e` because it crosses Web, API, broker, ML, persistence,
and browser boundaries rather than belonging to Web internals.

## Configuration

`PORTFOLIO_API_BASE_URL` is required by the server-side proxy. In Compose it is
`http://api:8000`; for host-side development it is normally
`http://127.0.0.1:58000`. `PORTFOLIO_WEB_UPSTREAM_TIMEOUT_MS` is optional and
defaults to 8000 milliseconds.

Run the app from the repository root after installing the pinned workspace:

```console
pnpm --filter @reactorfront/web dev
```

The development server is available at `http://127.0.0.1:3000` by default.
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
