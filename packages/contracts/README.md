# Shared contracts

## Intended responsibility

This package area will contain language-neutral contracts shared across service
boundaries.

Possible contents include OpenAPI documents, JSON Schema, event schemas, error
codes, and generated clients or types.

## Boundary rules

- Do not place business logic or unrelated helper functions here.
- Prefer one canonical schema over manually duplicated TypeScript and Python
  models.
- Treat contract changes as reviewable compatibility decisions.
- Generated files must identify their source and generation command.

## Accepted initial direction

- OpenAPI 3.1 is canonical for synchronous API contracts.
- JSON Schema is canonical for asynchronous event payloads.
- Requested, started, completed, and failed processing events are versioned and
  carry event, correlation, document, and job identifiers.
- The web application consumes generated TypeScript types or a generated client.
- Contract and event names are explicitly versioned.

The exact generator and any package-publishing strategy remain implementation
decisions. Generated output must be reproducible and checked for drift in CI.
