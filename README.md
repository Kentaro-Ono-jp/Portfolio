# ReactorFront Portfolio

> Status: first vertical slice completed — 2026-07-20

[![Verify](https://github.com/Kentaro-Ono-jp/Portfolio/actions/workflows/verify.yml/badge.svg)](https://github.com/Kentaro-Ono-jp/Portfolio/actions/workflows/verify.yml)

> AI-assisted work starts with [`GIT_AGENTS.md`](GIT_AGENTS.md).

This repository is ReactorFront's public engineering portfolio. It is not a
static profile site or a collection of disconnected demos. It will contain one
reproducible, production-oriented system that exposes product reasoning,
application development, applied ML, architecture, security, testing, and
operations as reviewable evidence.

## Product direction

The selected product is a **Document Intelligence and Human Review Platform**.
It will accept PDFs and images, run asynchronous ML processing, produce
structured results, and let authenticated users review and correct those
results with traceable audit events.

Only public, permissively licensed, or synthetic documents and datasets will
be used. Private client or employer materials are outside the project scope.

## Engineering evidence

The completed first vertical slice demonstrates:

- strict TypeScript and React/Next.js application development
- Python API and applied PyTorch ML engineering
- explicit OpenAPI and asynchronous-event contracts
- PostgreSQL, object storage, and durable job processing
- Docker Compose-based reproducibility
- tests, static analysis, supply-chain checks, and GitHub Actions verification
- observability, failure diagnosis, migrations, and recovery design
- focused issues, pull requests, ADRs, and release history

## Repository structure

```text
Portfolio/
|-- apps/
|   |-- web/                 # TypeScript web application
|   |-- api/                 # Python backend API
|   `-- ml/                  # ML inference and evaluation application
|-- packages/
|   `-- contracts/           # Language-neutral cross-service contracts
|-- docs/
|   |-- ai/                  # AI collaboration contract and prompt evidence
|   |-- architecture/        # Architecture documentation
|   |-- adr/                 # Architecture Decision Records
|   `-- delivery/            # Accepted delivery specifications
|-- tests/
|   |-- integration/         # Cross-service integration tests
|   `-- e2e/                 # Whole-system browser tests
|-- infra/
|   `-- docker/              # Docker-related supporting material
|-- scripts/                 # Shared execution and verification entrypoints
`-- .github/
    `-- workflows/           # GitHub Actions workflows
```

## Accepted architecture decisions

- [ADR-0001: Adopt a modular monorepo](docs/adr/0001-modular-monorepo.md)
- [ADR-0002: Target an AI-enabled document intelligence platform](docs/adr/0002-target-document-intelligence-platform.md)
- [ADR-0003: Adopt the initial technology stack](docs/adr/0003-initial-technology-stack.md)
- [ADR-0004: Keep state ownership in the API and use a transactional outbox](docs/adr/0004-api-state-ownership-and-transactional-outbox.md)
- [ADR-0006: Consolidate repository-owned AI guidance](docs/adr/0006-consolidate-ai-guidance.md)

Superseded decisions remain under [`docs/adr/`](docs/adr/README.md) as design
history.

## Delivery specifications

- [Delivery Specification 0001: First end-to-end vertical slice](docs/delivery/0001-first-vertical-slice.md)

## Contributing and security

- Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before proposing a change.
- Report vulnerabilities through the private process in
  [`SECURITY.md`](SECURITY.md), never through a public Issue.
- Use only repository-owned synthetic fixtures. Do not submit client,
  employer, personal, or otherwise confidential documents.

## AI-assisted engineering evidence

The repository treats AI collaboration rules and reusable prompts as reviewed
engineering artifacts rather than machine-local memory. The explicit
[`GIT_AGENTS.md`](GIT_AGENTS.md) entrypoint routes implementation work to the
consolidated [`docs/ai/README.md`](docs/ai/README.md) contract and review work
to [`docs/ai/PR_REVIEW.md`](docs/ai/PR_REVIEW.md).

The independent reviewer uses an isolated temporary shallow clone, runs
non-Docker static verification, and has comment-only GitHub write authority.
Fast-changing status remains in Issue #1, focused Issues, PRs, commits, and
Actions runs instead of being duplicated across local handoffs. Raw chats,
hidden reasoning, personal data, and private context are not published.

## Verification model

GitHub Actions will be the authoritative build and runtime verification
environment. Local Docker Desktop is a development convenience only.

The root [`compose.yaml`](compose.yaml) owns the isolated Compose project
`reactorfront-portfolio`. The canonical verifier checks contracts, generated
types, Web linting, formatting, static types, coverage, production dependency
advisories, migrations, unit tests, and a real
Web/HTTP/PostgreSQL/S3-compatible/RabbitMQ integration path in GitHub Actions.

Install the pinned dependencies and run local static verification from the
repository root. The static-only path neither resolves nor invokes the Docker
CLI. AI-agent work does not start or mutate local Docker Desktop:

```console
pnpm install --frozen-lockfile
uv sync --project apps/api --frozen
uv sync --project apps/ml --frozen
python scripts/verify.py --static-only
```

GitHub Actions runs `python scripts/verify.py` without the flag. That full path
builds and starts only this repository's Compose project, proves the complete
eight-service environment and browser E2E, and stops the project afterward. A
human reviewer may deliberately run the same full command with local Docker,
but it is not the default AI-agent workflow:

```console
python scripts/verify.py
```

### Run the current Web, API, outbox, result-consumer, and ML worker boundary

Start the three dependencies, create the deterministic development bucket,
then start the migrated API, its outbox dispatcher, result consumer, and the ML
worker:

```console
docker compose -p reactorfront-portfolio up --detach --build --wait postgres minio rabbitmq
uv run --project apps/api python scripts/prepare_integration.py
docker compose -p reactorfront-portfolio up --detach --build --wait api
docker compose -p reactorfront-portfolio up --detach --build --wait api-outbox
docker compose -p reactorfront-portfolio up --detach --build --wait api-events
docker compose -p reactorfront-portfolio up --detach --build --wait ml-worker
docker compose -p reactorfront-portfolio up --detach --build --wait web
```

The Web application is available at `http://127.0.0.1:53000` and the API at
`http://127.0.0.1:58000`. Required development ports bind only to loopback and
can be changed with the safe examples in
[`.env.example`](.env.example). The MinIO console is intentionally not
published to the host.

Submit a PDF of at most 5 MiB:

```console
curl --request POST http://localhost:58000/api/v1/documents \
  --header "X-Correlation-ID: 11111111-1111-4111-8111-111111111111" \
  --form "file=@sample.pdf;type=application/pdf"
```

## Completed first vertical slice

The first vertical slice is complete and remains traceable through
[Issue #1](https://github.com/Kentaro-Ono-jp/Portfolio/issues/1),
[Issue #24](https://github.com/Kentaro-Ono-jp/Portfolio/issues/24), and
[PR #25](https://github.com/Kentaro-Ono-jp/Portfolio/pull/25), with the final
delivery record published through
[PR #26](https://github.com/Kentaro-Ono-jp/Portfolio/pull/26). The independently
reviewed implementation head passed the complete nine-group clean-runner
[verification](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29731595926),
and the exact squash merge passed the default-branch
[workflow](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29734332826).

The contract, API-owned document submission, transactional outbox, independent
ML worker, API-owned result persistence, and Web upload/progress/result
boundaries are implemented. The
worker proves canonical Celery task consumption, source-integrity checks,
single-page PDF extraction, reproducible CPU PyTorch classification, and
confirmed at-least-once started/completed/failed result publication. The
`api-events` role validates those messages, commits event receipts and job
transitions atomically, deduplicates logical redelivery, and exposes processing,
completed, or failed state through the existing API.

The Web uses generated OpenAPI types plus runtime Zod validation, keeps the API
base URL server-only behind same-origin route handlers, and presents accessible
queued, processing, completed, failed, retry, and reset states. The final
verification adds Playwright coverage for the real browser upload,
completed invoice result, terminal ML failure, invalid-file rejection, and
cross-service correlation evidence against the complete eight-service Compose
environment. A final manual full
[main verification](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29734521272)
re-proved the completed tree without maintainer-specific state. After the
`main` Actions caches were removed, a second
[cold-cache dispatch](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29735196072)
re-proved the same exact tree. Repository-owned AI collaboration is defined by
[ADR-0006](docs/adr/0006-consolidate-ai-guidance.md) and `docs/ai/`.

## License

Copyright (c) 2026 Kentaro Ono (ReactorFront).

Original source code, documentation, and synthetic fixtures in this repository
are licensed under the [MIT License](LICENSE) unless a file states otherwise.
Third-party dependencies, assets, datasets, and models remain subject to their
respective licenses; introduced runtime infrastructure is recorded in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
