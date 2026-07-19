# Project scripts

This directory will provide a small number of platform-conscious entrypoints
for setup, verification, seed data, and diagnostics.

The accepted first-slice specification names `scripts/verify.py` as the
canonical verification entrypoint used by humans, coding agents, and GitHub
Actions.

Run it from the repository root after installing the two pinned dependency
sets:

```console
pnpm install --frozen-lockfile
uv sync --project apps/api --frozen
python scripts/verify.py
```

The default path validates repository structure and then starts only the
`reactorfront-portfolio` Compose project for migration, API-image, PostgreSQL,
S3-compatible, RabbitMQ, publisher-confirm, duplicate-delivery, and restart
recovery checks. It stops that project afterward. GitHub Actions also removes
the three project-scoped test volumes; local execution preserves them. A failed
teardown makes verification fail, and the workflow has an unconditional
project-scoped teardown step as a final safety net.

On runtime failure, the verifier writes sanitized Compose state, timestamped
service logs, JUnit output, and coverage XML under
`artifacts/verification/`. GitHub Actions uploads that directory before its
unconditional teardown step.

Use the non-container path when Docker is intentionally unavailable:

```console
python scripts/verify.py --static-only
```

Supporting scripts are implementation details of that entrypoint:

- `check_docs.py` rejects broken local Markdown links.
- `check-generated-contract.mjs` regenerates API types and detects content drift
  without confusing valid uncommitted output with stale output.
- `prepare_integration.py` idempotently creates the deterministic S3 test
  bucket after MinIO is healthy.
- `verify_outbox_runtime.py` proves expired-lease recovery, dispatcher restart,
  RabbitMQ restart, persistent delivery, and the queued-state transition.
- `validate-openapi.mjs` proves valid state variants and rejects impossible
  document states or unstable problem-response combinations.
- `validate-events.mjs` validates canonical event examples and representative
  rejection cases against the versioned JSON Schemas.
- `stamp-generated-contract.mjs` records the canonical source and regeneration
  command in the generated TypeScript contract header.
