# ADR-0004: Keep state ownership in the API and use a transactional outbox

- Status: Accepted
- Date: 2026-07-18

## Context

The API and ML worker are independently deployable areas. Allowing both areas
to read and write the same PostgreSQL schema would create an undocumented
shared-database contract and weaken the boundary established by ADR-0001.

The upload flow also needs to persist a document and processing job while
publishing work to RabbitMQ. A direct database commit followed by a broker
publish creates a dual-write failure window: the process can fail after the
database commit and before the message is durably published, leaving a job that
will never run.

The first vertical slice promises durable, observable job states and safe
at-least-once processing, so these failures must be designed before code is
introduced.

## Decision

### State ownership

`apps/api` is the sole owner of the PostgreSQL application schema. The web and
ML applications do not receive database credentials and do not access API
tables directly.

The API image may run separate process roles, but they remain part of the same
deployable area and use the same API-owned domain and persistence code:

- `api`: synchronous HTTP interface
- `api-outbox`: pending-event dispatcher
- `api-events`: processing-status and result-event consumer

### Upload transaction and compensation

The API validates the source and writes it to an application-owned object key.
It then uses one PostgreSQL transaction to insert:

- the document record
- a processing job in `accepted` state
- a `document.processing.requested.v1` outbox event

If the database transaction fails after object upload, the API attempts to
delete the unreferenced object and records a correlated error if compensation
also fails. An object-reconciliation mechanism may be added later if evidence
shows that best-effort compensation is insufficient.

### Transactional outbox

`api-outbox` leases unpublished outbox rows and publishes persistent messages
to RabbitMQ using publisher confirmation. After confirmation it records the
outbox row as published and advances the job from `accepted` to `queued` in one
database transaction.

If publishing succeeds but the database update fails, the same event may be
published again. Therefore delivery is explicitly at least once rather than
exactly once.

### ML processing and result events

`ml-worker` consumes the requested event through Celery, reads the document
from object storage, and performs deterministic processing. It publishes
versioned status or terminal events back to RabbitMQ:

- `document.processing.started.v1`
- `document.processing.completed.v1`
- `document.processing.failed.v1`

The worker acknowledges the requested task only after the required status or
terminal event has been confirmed by the broker. It never writes PostgreSQL.

`api-events` validates these events and applies state changes idempotently.
Event identifiers are unique, job transitions are checked, and repeated events
must not create a second terminal result.

### Contract and delivery rules

- Event payloads use versioned JSON Schemas under `packages/contracts`.
- `eventId`, `correlationId`, `documentId`, and `jobId` cross every boundary.
- Broker delivery is at least once.
- Database writes and state transitions are idempotent.
- Raw broker or worker exceptions are not exposed through the public API.
- The first slice runs one API event consumer to keep event-order behavior easy
  to inspect; later concurrency requires explicit ordering tests.

## Consequences

### Positive

- PostgreSQL has one clear owning application.
- A process crash cannot silently lose a committed processing request.
- ML and API remain coupled through documented events rather than shared code
  or a shared database schema.
- At-least-once behavior and duplicate handling become visible, testable
  architecture evidence.
- The same API image can provide HTTP, outbox, and event-consumer roles without
  creating another source repository or deployable boundary.

### Costs

- The first Compose topology gains `api-outbox` and `api-events` process roles.
- State progression includes `accepted` before `queued`.
- Outbox leasing, publisher confirmation, event validation, and idempotency
  require integration tests.
- Object storage and PostgreSQL still cannot share one transaction, so upload
  compensation and orphan diagnostics remain necessary.

## Rejected alternatives

- Let the ML worker write API-owned PostgreSQL tables directly.
- Commit the job and then publish directly from the HTTP request without
  recovery.
- Publish first and commit the job afterward, allowing workers to observe a
  missing job.
- Claim exactly-once delivery over PostgreSQL and RabbitMQ.
- Add Kafka only to obtain transactional messaging for this initial scale.

## Revisit when

- measured outbox latency or throughput requires a different dispatch method
- a workflow engine replaces the explicit job-state implementation
- the ML application becomes an independently owned product with its own state
- real deployment security requires broker or object-store credentials to be
  separated more strictly
