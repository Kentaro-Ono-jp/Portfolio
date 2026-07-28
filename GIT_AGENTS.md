# Repository guidance for AI agents

<!-- ips-role: router -->

This is the thin, tracked entrypoint for AI-assisted work in this repository.
It selects guidance; it is not the complete operating manual.

## Start

1. Read the [iPS Microkernel work router](ips-microkernel/work-router.md).
2. Select the first matching state there and open only that route.
3. Follow one explicit next or return transition at a time. Do not preload
   sibling workflows, reference files, accepted design records, CI history, or
   the human-only architecture README.

Use the [tool-neutral pointer](AI_GUIDANCE.md) only to reach this file. It is
not another source of rules.

## Non-negotiable product boundaries

- Implement only accepted design. A material product or structural change
  requires an ADR or delivery-specification change in the same reviewed work.
- Keep `apps/web`, `apps/api`, and `apps/ml` independently deployable.
- Do not import another deployable area's private implementation.
- Keep cross-language contracts, not shared business logic, in
  `packages/contracts`.
- Use explicit, documented interfaces between deployable areas.
- Keep cross-service integration and end-to-end tests outside service
  internals.

## Verification and Docker

- Use `python scripts/verify.py` as the only root verification entrypoint.
- GitHub Actions is authoritative for Docker-backed runtime proof.
- AI-agent local verification is static-only. Route every Docker-backed group
  to GitHub Actions instead of requesting local Docker access.
- The Compose project is `reactorfront-portfolio`. Never use global Docker
  cleanup or prune commands.
- A complete staged candidate enters the thin
  [CI router](ips-microkernel/ci/router.md); it does not load every CI
  procedure or historical failure record.

## Public boundary

Commit only portable, project-relevant material. Exclude credentials, private
source or company context, personal facts, machine-specific paths, raw chats,
hidden reasoning, and unfiltered local-memory exports. Use repository-owned
synthetic fixtures and preserve applicable licensing.

## Discrepancy recovery

When the workspace is unexpectedly dirty, a required head moved, live evidence
contradicts the focused scope, an unknown actor changed durable state,
automation gained unrecorded authority, or routing has no single matching
state, preserve the smallest relevant discrepancy and use the routed
live-state recovery. Never reset or discard unrelated work. Request a decision
only when recovery requires selecting or materially redefining the focused
slice.
