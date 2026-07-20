# Project scripts

This directory will provide a small number of platform-conscious entrypoints
for setup, verification, seed data, and diagnostics.

The accepted first-slice specification names `scripts/verify.py` as the
canonical verification entrypoint used by humans, coding agents, and GitHub
Actions.

After a complete implementation and its verification changes are staged but
not committed, use the
[GitHub Actions CI playbook](../.github/workflows/CI_PLAYBOOK.md) to harden the
candidate without changing what the accepted test must prove. Reverify and
restage any correction before commit.

Run it from the repository root after installing the pinned dependency sets:

```console
pnpm install --frozen-lockfile
uv sync --project apps/api --frozen
uv sync --project apps/ml --frozen
python scripts/verify.py
```

The default path validates repository structure and then starts only the
`reactorfront-portfolio` Compose project for migration, API and ML images,
PostgreSQL, S3-compatible storage, RabbitMQ, publisher-confirm, model, Web,
result-event persistence, duplicate-delivery, and restart-recovery checks. It
stops that project afterward.
GitHub Actions also removes
the three project-scoped test volumes; local execution preserves them. A failed
teardown makes verification fail, and the workflow has an unconditional
project-scoped teardown step as a final safety net.

On runtime failure, the verifier writes sanitized Compose state, timestamped
service logs, Web, ML, and API event-consumer readiness output, JUnit output,
model/runtime proof, result-persistence proof, and branch-aware coverage XML
under `artifacts/verification/`. GitHub Actions uploads that directory before its
unconditional teardown step.

Use the non-container path when Docker is intentionally unavailable:

```console
python scripts/verify.py --static-only
```

Supporting scripts are implementation details of that entrypoint:

- `check_docs.py` rejects broken local Markdown links and drift in the required
  repository-owned AI governance topology, critical review boundaries, agent
  entrypoint references, and public-safe path rules.
- `check_ml_compose_boundary.py` proves the CPU-only lock, keeps the worker free
  of database settings and host ports, verifies that `api-events` remains a
  separate API-owned role, and constrains Web to the internal API boundary.
- `apps/ml/audit-requirements.txt` normalizes the CPU wheel's local version label
  so pip-audit can check the corresponding public PyTorch advisory identity;
  the verifier rejects drift from `pyproject.toml`.
- `check-generated-contract.mjs` regenerates API types and detects content drift
  without confusing valid uncommitted output with stale output.
- `prepare_integration.py` idempotently creates the deterministic S3 test
  bucket after MinIO is healthy.
- `pdf_fixture.py` builds deterministic, repository-owned single-page text PDFs.
- `verify_ml_model.py` proves independent model generations, checksum metadata,
  and real CPU PyTorch inference.
- `verify_ml_runtime.py` proves the real API-to-outbox-to-worker path, source
  integrity, result contracts, stable failure, duplicate delivery, persistent
  result messages, and RabbitMQ/worker recovery.
- `verify_result_consumer_runtime.py` proves outbox/result ordering recovery,
  atomic API-owned receipts and terminal persistence, logical deduplication,
  poison/conflict rejection, broker/consumer restart, and dependency readiness.
- `verify_outbox_runtime.py` proves expired-lease recovery, dispatcher restart,
  RabbitMQ restart, persistent delivery, and the queued-state transition.
- `validate-openapi.mjs` proves valid state variants and rejects impossible
  document states or unstable problem-response combinations.
- `validate-events.mjs` validates canonical event examples and representative
  rejection cases against the versioned JSON Schemas.
- `stamp-generated-contract.mjs` records the canonical source and regeneration
  command in the generated TypeScript contract header.
