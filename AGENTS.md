# Project guidance for coding agents

## Current phase

The product direction, modular-monorepo boundary, initial technology stack, and
first vertical slice are accepted. Implement only against the accepted ADRs and
delivery specification. Do not add or replace technology merely for breadth;
material changes require an ADR or specification update in the same change.

Before application coding, satisfy the `Pre-implementation gates` in Delivery
Specification 0001. Recheck live Git and GitHub state rather than assuming an
older readiness snapshot is still current.

## Source of truth

Read these documents before making structural changes:

1. `README.md`
2. Accepted ADRs under `docs/adr/`, in numeric order
3. `docs/delivery/0001-first-vertical-slice.md`
4. The nearest area-specific `README.md`

When a structural decision changes, update or supersede the relevant ADR in the
same change.

## Repository boundaries

- `apps/web`, `apps/api`, and `apps/ml` are independently deployable areas.
- Deployable areas must not import another area's internal implementation.
- `packages/contracts` contains cross-language contracts, not shared business
  logic or unrelated helpers.
- Cross-service communication must use an explicit, documented interface.
- Keep integration and end-to-end tests outside individual service internals.

## Docker safety

- The Compose project name is `reactorfront-portfolio`.
- Do not add `container_name` without a documented requirement.
- Do not declare existing Docker volumes or networks as external without an
  explicit task requirement.
- Never run global Docker cleanup or prune commands for this repository.
- Scope Docker operations to this Compose project and show exact targets before
  destructive cleanup.

## Public repository safety

- Never add real credentials, tokens, private source code, private company
  information, or machine-specific secrets.
- Use safe examples and `.env.example` for configuration documentation.
- Prefer deterministic, redistributable sample data.
- Preserve the standard root MIT License text without custom restrictions.
- Treat third-party dependencies, assets, datasets, and models as separately
  licensed and document them when they are introduced.

## Verification

Use `python scripts/verify.py` as the canonical verification entrypoint for
humans, coding agents, and GitHub Actions. Install the pinned JavaScript
dependencies with `pnpm install --frozen-lockfile` before running it.

Until services exist, this entrypoint validates canonical contracts, generated
type drift, documentation links, and `docker compose config` without starting
Docker. Expand this same entrypoint as runnable services are introduced; do not
create a competing verification path.
