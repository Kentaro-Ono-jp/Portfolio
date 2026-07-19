# ReactorFront Portfolio

> Status: first vertical slice in implementation — 2026-07-19

[![Verify](https://github.com/Kentaro-Ono-jp/Portfolio/actions/workflows/verify.yml/badge.svg)](https://github.com/Kentaro-Ono-jp/Portfolio/actions/workflows/verify.yml)

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

The completed repository is intended to demonstrate:

- strict TypeScript and React/Next.js application development
- Python API and applied PyTorch ML engineering
- explicit OpenAPI and asynchronous-event contracts
- PostgreSQL, object storage, and durable job processing
- Docker Compose-based reproducibility
- tests, static analysis, supply-chain checks, and GitHub Actions verification
- observability, failure diagnosis, migrations, and recovery design
- AWS and Terraform architecture with documented tradeoffs
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
|   |-- architecture/        # Architecture documentation
|   `-- adr/                 # Architecture Decision Records
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

## Delivery specifications

- [Delivery Specification 0001: First end-to-end vertical slice](docs/delivery/0001-first-vertical-slice.md)

## Verification model

GitHub Actions will be the authoritative build and runtime verification
environment. Local Docker Desktop is a development convenience only.

The root [`compose.yaml`](compose.yaml) owns the isolated Compose project
`reactorfront-portfolio`. The canonical verifier checks contracts, generated
types, linting, formatting, static types, migrations, unit tests, and a real
HTTP/PostgreSQL/S3-compatible/RabbitMQ integration path in GitHub Actions.

Install the pinned dependencies and run the same verification from the
repository root:

```console
pnpm install --frozen-lockfile
uv sync --project apps/api --frozen
uv sync --project apps/ml --frozen
python scripts/verify.py
```

The full command builds and starts only this repository's Compose project and
stops it afterward. To run all checks without starting containers:

```console
python scripts/verify.py --static-only
```

### Run the current API, outbox, and ML worker boundary

Start the three dependencies, create the deterministic development bucket,
then start the migrated API, its outbox dispatcher, and the ML worker:

```console
docker compose -p reactorfront-portfolio up --detach --build --wait postgres minio rabbitmq
uv run --project apps/api python scripts/prepare_integration.py
docker compose -p reactorfront-portfolio up --detach --build --wait api
docker compose -p reactorfront-portfolio up --detach --build --wait api-outbox
docker compose -p reactorfront-portfolio up --detach --build --wait ml-worker
```

The API is available at `http://127.0.0.1:58000`. Required development ports
bind only to loopback and can be changed with the safe examples in
[`.env.example`](.env.example). The MinIO console is intentionally not
published to the host.

Submit a PDF of at most 5 MiB:

```console
curl --request POST http://localhost:58000/api/v1/documents \
  --header "X-Correlation-ID: 11111111-1111-4111-8111-111111111111" \
  --form "file=@sample.pdf;type=application/pdf"
```

## Current stage

The public documentation baseline is published. Implementation of the first
vertical slice is tracked in
[Issue #1](https://github.com/Kentaro-Ono-jp/Portfolio/issues/1) and proceeds
through focused, reviewable pull requests.

The contract, API-owned document submission, and transactional outbox
foundations are merged. The current focused increment implements the independent
ML worker boundary: canonical Celery task consumption, source-integrity checks,
single-page PDF extraction, reproducible CPU PyTorch classification, and
confirmed at-least-once started/completed/failed result publication. The API
result consumer and the Web application remain later increments.

## License

Copyright (c) 2026 Kentaro Ono (ReactorFront).

Original source code, documentation, and synthetic fixtures in this repository
are licensed under the [MIT License](LICENSE) unless a file states otherwise.
Third-party dependencies, assets, datasets, and models remain subject to their
respective licenses; introduced runtime infrastructure is recorded in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
