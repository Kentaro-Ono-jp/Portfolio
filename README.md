# ReactorFront Portfolio

> Status: first vertical slice accepted for implementation — 2026-07-18

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

The root [`compose.yaml`](compose.yaml) currently reserves the isolated Compose
project name `reactorfront-portfolio`; services will be added through focused
vertical-slice changes. A shared verification entrypoint will be introduced
before the first executable slice.

## Current stage

The repository has an accepted product direction, module boundary, and initial
technology stack. The first vertical slice and its acceptance criteria have
status `Accepted`. No application dependencies or runnable services have been
introduced yet.

The next gate is to initialize and publish the documentation baseline as its
own Git history before application implementation begins. Implementation then
proceeds through focused, reviewable changes that keep the accepted delivery
specification and canonical CI proof synchronized.

## License

Copyright (c) 2026 Kentaro Ono (ReactorFront).

Original source code, documentation, and synthetic fixtures in this repository
are licensed under the [MIT License](LICENSE) unless a file states otherwise.
Third-party dependencies, assets, datasets, and models remain subject to their
respective licenses.
