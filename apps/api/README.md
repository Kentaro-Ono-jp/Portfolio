# API application boundary

## Intended responsibility

This area will expose the backend API and coordinate application use cases.

## Boundary rules

- Expose explicit, versioned interfaces to external consumers.
- Do not import web implementation details.
- Communicate with ML capabilities through a documented interface rather than
  importing ML internals.
- Keep transport concerns separate from application and domain logic when the
  concrete design is introduced.

## Accepted initial direction

- Python with FastAPI and Pydantic
- Versioned REST endpoints described by OpenAPI 3.1
- PostgreSQL with SQLAlchemy and Alembic
- API-owned PostgreSQL state; ML processes receive no database credentials
- a transactional outbox dispatcher for processing requests
- a RabbitMQ event consumer for idempotent processing-state updates
- Celery and RabbitMQ for at-least-once asynchronous ML processing
- pytest, Ruff, and static type checking

Exact runtime and package versions will be pinned after compatibility checks.
Authentication and authorization are deliberately deferred beyond the first
vertical slice.
