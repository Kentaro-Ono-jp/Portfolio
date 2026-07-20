# Shared contracts

## Responsibility

This package contains the language-neutral contracts shared across service
boundaries:

- `openapi/openapi.yaml`: canonical OpenAPI 3.1 synchronous API contract
- `events/*.schema.json`: canonical JSON Schema event contracts
- `examples/events/*.json`: deterministic valid event examples
- `generated/api.d.ts`: generated TypeScript API types

## Boundary rules

- Do not place business logic or unrelated helper functions here.
- Prefer one canonical schema over manually duplicated TypeScript and Python
  models.
- Treat contract changes as reviewable compatibility decisions.
- Generated files must identify their source and generation command.

## Accepted initial direction

- OpenAPI 3.1 is canonical for synchronous API contracts.
- JSON Schema is canonical for asynchronous event payloads.
- Requested, started, completed, and failed processing events are versioned and
  carry event, correlation, document, and job identifiers.
- The web application consumes generated TypeScript types or a generated client.
- Contract and event names are explicitly versioned.

## Requested-event RabbitMQ transport

The API-owned outbox dispatcher publishes requested work through this durable
direct topology:

| Element | Value |
|---|---|
| Exchange | `reactorfront.documents.v1` |
| Queue | `reactorfront.document-processing.requested.v1` |
| Routing key | `document.processing.requested.v1` |
| Celery task | `reactorfront_ml.process_document` |

The broker message uses Celery protocol v2 with JSON encoding. The canonical
`document.processing.requested.v1` object is the first positional task
argument; it is not replaced by a private Python model. The outbox `eventId`
is both the Celery task ID and AMQP message ID. The application
`correlationId` is carried as the Celery root ID and an explicit header.

The exchange and queue are durable, messages use persistent delivery mode,
routing is mandatory, and the dispatcher waits for publisher confirmation.
Confirmation followed by an unknown database result may publish the same event
again, so consumers must treat `eventId` idempotently. This boundary does not
claim exactly-once delivery.

## Result-event RabbitMQ transport

The ML worker publishes processing observations through the same durable direct
exchange. The queue is declared now so publication can be proved before the
later API-owned consumer exists.

| Element | Value |
|---|---|
| Exchange | `reactorfront.documents.v1` |
| Queue | `reactorfront.document-processing.events.v1` |
| Started routing key | `document.processing.started.v1` |
| Completed routing key | `document.processing.completed.v1` |
| Failed routing key | `document.processing.failed.v1` |

Each message body is the canonical JSON object validated against its versioned
schema. The AMQP message ID equals the canonical `eventId`; correlation,
document, and job identifiers are preserved in the payload and message
metadata. Events use persistent delivery, mandatory routing, and bounded
publisher confirms. The requested task is acknowledged only after the required
result event confirms.

Duplicate requested delivery may produce duplicate result messages. Logical
event IDs are deterministic for the requested event and result type. The
API-owned `api-events` consumer stores one receipt per logical ID and compares
an immutable-payload digest before treating redelivery as a no-op. Only
`occurredAt` is excluded from that digest because a legitimate republication
records a new observation time. Receipt and job mutation commit atomically,
and acknowledgement follows that commit. The transport remains explicitly at
least once and does not claim exactly-once publication.

## Verification and generation

From the repository root:

```console
pnpm contracts:check
```

The command lints OpenAPI, validates valid and impossible API response states,
validates positive and negative event examples, regenerates
`generated/api.d.ts`, and fails when committed generated output has drifted.
Generate the TypeScript output alone with:

```console
pnpm contracts:generate
```

The package remains private workspace infrastructure. A publishing strategy is
deferred until an external consumer requires one.
