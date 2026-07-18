# Architecture documentation

This directory will explain the system from context to implementation.

The selected product is a Document Intelligence and Human Review Platform.
It will accept documents, execute asynchronous ML processing, expose structured
results, and support authenticated human review with traceable audit events.

Planned documentation may include:

- System context and target users
- Container and component diagrams
- Service responsibilities and trust boundaries
- Request, job, and data-flow sequences
- Deployment and runtime topology
- Failure modes and operational recovery

The repository defines three deployable areas (`web`, `api`, and `ml`) plus one
shared contract area. Synchronous APIs use OpenAPI 3.1, and asynchronous event
payloads use JSON Schema. PostgreSQL is the transactional system of record,
S3-compatible storage owns document artifacts, and Celery workers initially use
RabbitMQ for at-least-once job and result-event delivery. The API owns the
PostgreSQL schema; ML workers do not access it. A transactional outbox closes
the database-to-broker dual-write gap.

Accepted decisions:

- [ADR-0001: Adopt a modular monorepo](../adr/0001-modular-monorepo.md)
- [ADR-0002: Target an AI-enabled document intelligence platform](../adr/0002-target-document-intelligence-platform.md)
- [ADR-0003: Adopt the initial technology stack](../adr/0003-initial-technology-stack.md)
- [ADR-0004: Keep state ownership in the API and use a transactional outbox](../adr/0004-api-state-ownership-and-transactional-outbox.md)

Accepted delivery specifications:

- [Delivery Specification 0001: First end-to-end vertical slice](../delivery/0001-first-vertical-slice.md)
