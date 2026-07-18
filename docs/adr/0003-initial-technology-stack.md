# ADR-0003: Adopt the initial technology stack

- Status: Accepted
- Date: 2026-07-18

## Context

The selected product needs meaningful TypeScript and Python, durable document
and job processing, explicit contracts, ML evaluation, observable operations,
and a credible path from Docker Compose to AWS.

The stack must be recognizable in current commercial work while remaining
small enough to implement and verify as one finished system. Technologies must
earn their place through a product or proof requirement; dependency count is
not itself evidence of architecture skill.

This ADR selects technology families. Exact versions will be pinned in lock
files and container images after compatibility checks. Stable releases are
preferred over previews.

## Decision

### Web application

- TypeScript with strict type checking
- React and the stable Next.js release line
- Tailwind CSS for application styling
- TanStack Query for server-state synchronization
- Zod for client-boundary validation where generated contracts are insufficient
- Vitest for focused tests and Playwright for browser-level tests

### Backend API

- Python and FastAPI
- Pydantic for request, response, configuration, and boundary validation
- SQLAlchemy and Alembic for persistence and schema migration
- pytest for tests, Ruff for linting and formatting, and static type checking

The API remains in Python rather than adding a TypeScript or Go backend. This
keeps the application and ML path coherent while still exposing meaningful
TypeScript in the web application and generated client boundary.

### ML application

- Python and PyTorch
- explicit, versioned preprocessing, inference, postprocessing, and evaluation
- a small real-inference path that can run in canonical CI verification
- external model artifacts kept out of normal Git history

An AI orchestration framework may be used behind an adapter if a proven use
case requires one. It must not become the product's domain model.

### Data and files

- PostgreSQL 18 as the transactional system of record
- S3-compatible object storage for source documents and generated artifacts
- MinIO as the initial Compose-compatible object-storage implementation

`pgvector` is not enabled until semantic retrieval is a confirmed product
requirement with an evaluation method.

### Asynchronous processing

- Celery workers with RabbitMQ as the initial message broker
- PostgreSQL as the authoritative job and result-state store
- idempotency, retry policy, timeout, cancellation, and failure state modeled
  explicitly in the application

Redis is not part of the initial stack. It may be added only for a measured
caching, coordination, or rate-limiting requirement.

### Contracts

- OpenAPI 3.1 as the canonical synchronous API description
- a generated TypeScript client and types for the web application
- JSON Schema for asynchronous event payloads
- no sharing of private application implementation between deployable areas

### Observability

- OpenTelemetry instrumentation and context propagation
- structured JSON logs with correlation identifiers
- Prometheus-compatible metrics and Grafana dashboards
- health, readiness, and dependency diagnostics

### Verification and supply-chain safety

- GitHub Actions as the authoritative verification environment
- Docker Compose for reproducible integration execution
- type checking, linting, unit, integration, end-to-end, and minimal real-ML tests
- CodeQL, dependency auditing, container scanning, secret scanning, and SBOM
  generation
- failure logs and useful diagnostics retained as CI artifacts

### Infrastructure and deployment path

- Docker Compose for development and canonical CI execution
- AWS as the first cloud design target
- Terraform for infrastructure as code
- ECS/Fargate, RDS for PostgreSQL, and S3 as the initial production topology

Kubernetes, Helm, and EKS are deferred until the complete Compose-based system
and its operational evidence exist. They may be added later as a separate
deployment proof, not as a prerequisite for the first working product.

## Consequences

### Positive

- The stack maps directly to the selected high-value engagement areas.
- TypeScript and Python are both exercised at meaningful system boundaries.
- The API, ML, database, queue, and object store form a realistic asynchronous
  document-processing system.
- Generated contracts reduce frontend/backend drift.
- Compose and GitHub Actions keep verification independent of the maintainer's
  local Docker Desktop.
- AWS and Terraform provide a credible production path without requiring an
  early Kubernetes platform.

### Costs

- RabbitMQ, MinIO, PostgreSQL, and multiple applications increase integration
  and startup-order complexity.
- Generated contracts need drift checks and deterministic generation.
- OpenTelemetry and security automation require maintenance across languages.
- The AWS topology will need explicit decisions for identity, secrets,
  networking, cost control, and asynchronous transport.

## Deferred technologies

Add these only when a requirement and verification method justify them:

- `pgvector` for evaluated semantic retrieval
- Redis for measured caching or coordination needs
- Kafka for demonstrated event replay or throughput requirements
- ONNX Runtime for proven inference portability or performance needs
- MLflow for a model lifecycle that cannot be represented cleanly otherwise
- Kubernetes and Helm for a later orchestration and deployment proof

## Rejected initial choices

- Go or Rust added only for language breadth
- GraphQL without a client-query problem that warrants it
- Kafka used as a generic queue
- Kubernetes used before a complete observable application exists
- microservice decomposition beyond the three current deployable areas
- an AI framework treated as the core architecture

## Revisit when

- product requirements invalidate one of the selected boundaries
- compatibility testing requires an earlier stable runtime or database version
- measurements justify one of the deferred technologies
- the Compose topology is complete and a Kubernetes proof has independent value
- the AWS target changes or a real deployment produces new constraints

## References

- [PostgreSQL 18](https://www.postgresql.org/about/press/presskit18/)
- [PyTorch releases](https://pytorch.org/blog/)
- [CNCF Annual Cloud Native Survey 2025](https://www.cncf.io/announcements/2026/01/20/kubernetes-established-as-the-de-facto-operating-system-for-ai-as-production-use-hits-82-in-2025-cncf-annual-cloud-native-survey/)
