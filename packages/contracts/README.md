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
