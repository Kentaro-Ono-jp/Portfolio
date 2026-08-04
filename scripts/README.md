# Project scripts

This directory will provide a small number of platform-conscious entrypoints
for setup, verification, seed data, and diagnostics.

The accepted first-slice specification names `scripts/verify.py` as the
canonical verification entrypoint used by humans, coding agents, and GitHub
Actions.

After a complete implementation and its verification changes are staged but
not committed, use the
[GitHub Actions CI router](../ips-microkernel/ci/router.md). Select only
staged preflight and any conditionally matching knowledge leaf; do not load CI
exceptions or historical failures by default. Reverify and restage every
correction before commit.

For AI-agent local work, run the static path from the repository root after
installing the pinned dependency sets:

```console
pnpm install --frozen-lockfile
uv sync --project apps/api --frozen
uv sync --project apps/ml --frozen
python scripts/verify.py --static-only
```

This static-only path selects the five non-Docker groups and does not resolve
or invoke the Docker CLI. Compose configuration and all runtime groups remain
GitHub Actions work for AI agents.

GitHub Actions runs the default path without `--static-only`. It validates
repository structure and then starts only the
`reactorfront-portfolio` Compose project for migration, API and ML images,
PostgreSQL, S3-compatible storage, RabbitMQ, publisher-confirm, model, Web,
result-event persistence, duplicate-delivery, restart-recovery, exact
nine-service readiness, and Playwright browser checks. It stops that project
afterward. AI agents never start or mutate local Docker Desktop; Docker-backed
proof runs in GitHub Actions.
GitHub Actions also removes
the three project-scoped test volumes; local execution preserves them. A failed
teardown makes verification fail, and the workflow has an unconditional
project-scoped teardown step as a final safety net.

On runtime failure, the verifier writes sanitized Compose state, timestamped
service logs, Web, ML, and API event-consumer readiness output, JUnit output,
model/runtime proof, result-persistence proof, and branch-aware coverage XML
under `artifacts/verification/`. Browser trace, video, screenshot, and HTML
containers stay in the non-uploaded `artifacts/private-verification/` boundary.
GitHub Actions uploads only the public directory before its unconditional
teardown step.

Use the non-container path when Docker is intentionally unavailable:

```console
python scripts/verify.py --static-only
```

Supporting scripts are implementation details of that entrypoint:

- `plan_ci.py` converts trusted GitHub event state into the canonical selective
  plan. It keeps baseline and current-head trust separate, closes inherited
  evidence gaps for external PRs, and routes tree-identical merges through the
  same skip-lineage rules as changed trees.
- `check_docs.py` rejects broken local Markdown links and drift in the routed
  AI-governance inventory, roles, canonical rule ownership, reachability,
  thin-router budgets, review boundaries, CI failure evidence, and public-safe
  path rules.
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
- `verify_principal_migration.py` upgrades a populated first-slice schema and
  proves that documents, jobs, outbox rows, and result receipts retain their
  identities while receiving only the controlled legacy-system principal.
- `verify_identity_runtime.py` follows Dex Authorization Code flow with PKCE,
  validates the real access token and capabilities both host-side and inside
  the API container through its backchannel, resolves one stable API principal,
  rejects a tampered signature, and proves the token is absent from persistence,
  logs, and evidence.
- `oidc_test_client.py` owns the dependency-free synthetic Authorization Code
  client shared by direct API and ML runtime verifiers; it stops at the
  repository-owned callback and never writes the access token to evidence.
- `check_identity_boundary.py` constrains the pinned Dex image, loopback-only
  exposure, authorization-code-only configuration, synthetic identity, and
  pinned JWT library.
- `pdf_fixture.py` builds deterministic, repository-owned single-page text PDFs.
- `verify_ml_model.py` proves independent model generations, checksum metadata,
  and real CPU PyTorch inference.
- `verify_ml_evaluation.py` reconstructs the immutable corpus and family-
  disjoint split; reproduces the champion baseline and snapshot-driven
  candidate artifact and report twice; validates the closed report and
  comparison schemas; recomputes promotion eligibility; rejects corrupted
  candidate lineage; and requires byte identity with every reviewed record.
- `verify_ml_runtime.py` obtains a synthetic OIDC access token and proves the
  authenticated API-to-outbox-to-worker path, source integrity, result
  contracts, stable failure, duplicate delivery, persistent result messages,
  and RabbitMQ/worker recovery.
- `verify_result_consumer_runtime.py` uses the same authenticated document
  boundary and proves outbox/result ordering recovery,
  atomic API-owned receipts and terminal persistence, logical deduplication,
  poison/conflict rejection, broker/consumer restart, and dependency readiness.
- `verify_outbox_runtime.py` uses a synthetic OIDC access token to prove
  expired-lease recovery, dispatcher restart, RabbitMQ restart, persistent
  delivery, and the queued-state transition.
- `tests/e2e/document-classification.spec.ts` proves browser-visible OIDC
  sign-in without browser token storage, private-source integrity, approval,
  synthetic correction, audit order, idempotent replay, stale/CSRF rejection,
  sign-out denial, failed processing, correlation propagation, and non-PDF
  rejection while Playwright retains trace, screenshot, video, and HTML output
  only under `artifacts/private-verification/`; sanitized JUnit and structured
  proof remain in `artifacts/verification/`.
- `sanitize_verification_artifacts.py` redacts then re-scans ordinary evidence
  and ZIP members for private-key, JWT, Web-session-cookie, CSRF-token,
  authorization-code, and bearer material. The browser proof also registers
  submitted-source, submitted-private-data, and static private-profile canaries
  before navigation, then registers received reviewer and audit-actor values
  before assertions can report them. Raw, standard-base64, URL-safe padded and
  unpadded, strict-percent, and lowercase-percent forms are removed and
  re-scanned without writing canary values to the report. Private browser
  containers in the public root close the upload gate. GitHub Actions uploads
  failure evidence only after this proof succeeds; failure cannot suppress
  project-scoped teardown.
- `validate-openapi.mjs` proves valid state variants and rejects impossible
  document states or unstable problem-response combinations.
- `validate-events.mjs` validates canonical event examples and representative
  rejection cases against the versioned JSON Schemas.
- `stamp-generated-contract.mjs` records the canonical source and regeneration
  command in the generated TypeScript contract header.
