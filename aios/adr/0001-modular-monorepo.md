# ADR-0001: Adopt a modular monorepo

- Status: Accepted
- Date: 2026-07-18

## Context

The portfolio must demonstrate frontend, backend, shared-contract, ML,
containerization, testing, and architecture skills as one coherent system.

Splitting those concerns into separate GitHub repositories immediately would
add cross-repository versioning, coordinated releases, CI orchestration, and
discovery overhead before independent release or ownership requirements exist.

At the same time, placing every concern in one undifferentiated source tree
would hide important service and language boundaries.

## Decision

Use one public GitHub repository with these logical areas:

- `apps/web`: independently deployable web application
- `apps/api`: independently deployable backend API
- `apps/ml`: independently deployable ML inference and evaluation application
- `packages/contracts`: language-neutral cross-service contracts

Keep repository-wide documentation, tests, infrastructure, scripts, and CI at
the root. Each deployable area may later own an independent Dockerfile and
dependency manifest.

Deployable areas must communicate through explicit interfaces and must not
import another area's private implementation.

## Consequences

### Positive

- One clone and one root Compose definition can reproduce the system.
- Cross-cutting changes can be reviewed in one pull request.
- Architecture boundaries remain visible without early release overhead.
- GitHub Actions can provide one authoritative integration result.
- A service can be extracted later if an actual boundary requires it.

### Costs

- CI must avoid running every check unnecessarily as the repository grows.
- Ownership and dependency rules need documentation and enforcement.
- Large ML artifacts must not make normal source checkout impractical.

## Revisit when

Consider extracting an area into a separate repository only when one or more of
these conditions become real:

- Independent release cadence or access control is required.
- Different maintainers need separate ownership and review policies.
- Build or checkout cost cannot be controlled inside the monorepo.
- ML models or data require a distinct artifact lifecycle.
- A service becomes a separately consumed product.

## Explicit non-decisions

This ADR does not select the product theme, frameworks, package managers,
database, queue, communication protocol, cloud provider, or hosting strategy.
