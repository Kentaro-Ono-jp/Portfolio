# Web application boundary

## Intended responsibility

This area will contain the user-facing web application.

## Boundary rules

- Consume backend capabilities through an explicit API contract.
- Do not access a database or ML implementation directly.
- Do not import internal source code from `apps/api` or `apps/ml`.
- Keep web-only presentation and interaction logic within this area.

## Accepted initial direction

- Strict TypeScript with React and the stable Next.js release line
- Tailwind CSS for styling
- TanStack Query for server state and Zod for client-boundary validation
- Vitest for focused tests and Playwright for browser-level tests
- Generated API types or client derived from the canonical OpenAPI document

Exact runtime and package versions will be pinned after compatibility checks.
Authentication is deliberately deferred beyond the first vertical slice.
