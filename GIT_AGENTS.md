# Repository guidance for AI agents

This is the explicit, tracked entrypoint for AI-assisted work in this
repository.

## Start here

1. Read [README.md](README.md).
2. Read [the AI collaboration contract](docs/ai/README.md).
3. Read accepted ADRs under [docs/adr](docs/adr/README.md), in numeric order.
4. Read [Delivery Specification 0001](docs/delivery/0001-first-vertical-slice.md).
5. Read the nearest area-specific README for the files in scope.
6. Read Issue #1 and only the focused Issue, PR, verdict, and Actions evidence
   needed for the current task.

Accepted ADRs and delivery specifications govern product and structural
design. Repository guidance governs durable collaboration. GitHub Issues,
PRs, commits, verdicts, and Actions runs govern live state. Local memory and
earlier conversations are orientation only.

## Non-negotiable boundaries

- Implement only accepted design. A material structural change requires an ADR
  or specification change in the same PR.
- Keep `apps/web`, `apps/api`, and `apps/ml` independently deployable.
- Do not import another deployable area's private implementation.
- Keep cross-language contracts, not shared business logic, in
  `packages/contracts`.
- Use explicit, documented interfaces between deployable areas.
- Keep cross-service integration and end-to-end tests outside service
  internals.

## Work modes

- Implementation, publication, merge, evidence, and cleanup follow
  [docs/ai/README.md](docs/ai/README.md).
- Initial PR review and re-review follow
  [docs/ai/PR_REVIEW.md](docs/ai/PR_REVIEW.md).
- Fast-changing status stays in the live GitHub ledger; do not create a tracked
  handoff or current-status duplicate.

## Verification and Docker

- Use `python scripts/verify.py` as the only root verification entrypoint.
- Install pinned JavaScript dependencies with
  `pnpm install --frozen-lockfile` before canonical verification.
- Use `python scripts/verify.py --static-only` when local runtime verification
  is not explicitly authorized.
- GitHub Actions is the authoritative runtime proof.
- The Compose project name is `reactorfront-portfolio`.
- Never use global Docker cleanup or prune commands. Scope operations and
  cleanup to this project.
- Do not add `container_name` or declare external networks or volumes without a
  documented requirement.

## Public repository safety

Commit only portable, project-relevant material. Never commit credentials,
tokens, private source or company context, personal facts, machine-specific
paths, raw chats, hidden reasoning, or local-memory exports. Use safe examples
and deterministic, redistributable data. Preserve the standard MIT License and
record third-party licensing when assets, data, models, or dependencies are
introduced.

## Stop conditions

Stop the pending mutation and report the smallest relevant discrepancy when
the workspace is unexpectedly dirty, a required head moved, live evidence
contradicts the focused scope, an unknown actor changed durable state, or
automation gained unrecorded authority. Never reset or discard unrelated work
to make the discrepancy disappear.
