# API application boundary

## Responsibility

This area exposes the backend API and coordinates API-owned application use
cases. It accepts and validates PDFs, stores source objects, atomically records
a document, processing job, and transactional outbox event, and dispatches the
committed event through an independently runnable API image role.

## Boundary rules

- Expose explicit, versioned interfaces to external consumers.
- Do not import web implementation details.
- Communicate with ML capabilities through a documented interface rather than
  importing ML internals.
- Keep transport concerns separate from application and domain logic.
- Keep PostgreSQL credentials inside API-owned roles; ML services never receive
  direct database access.

## Implemented boundary

- Python 3.13 with exact dependencies locked by uv
- FastAPI and Pydantic transport models
- SQLAlchemy 2 and PostgreSQL 18 persistence
- explicit Alembic migrations
- S3-compatible source-object storage through boto3
- canonical JSON Schema validation before outbox persistence
- safe PostgreSQL outbox leasing with process-unique ownership, attempt fencing,
  and expired-lease recovery
- persistent RabbitMQ publication with mandatory routing, publisher confirms,
  and a wall-clock confirmation deadline
- Celery protocol v2-compatible requested-task envelopes
- at-least-once retry with bounded backoff and stable event identity
- atomic post-confirm outbox publication and `accepted` to `queued` transition
- stable public problem responses without raw internal errors
- pytest, Ruff, strict mypy, pip-audit, and branch-aware coverage

The API writes the source object first, then inserts the document, accepted job,
and requested outbox event in one database transaction. A confirmed uncommitted
transaction triggers a best-effort object deletion. If the commit response is
lost, the repository observes all three persisted identities through a fresh
connection. Only a complete matching observation upgrades the request to
accepted; an immediate absence is not treated as rollback proof, so the source
is retained whenever the outcome remains unknown.
The submitted filename is display-only; the server creates the object key and
persists a SHA-256 digest.

The `api-outbox` role uses the same API-owned image and persistence code. It
leases only unpublished rows, publishes the canonical requested-event payload
inside a Celery-compatible task message, and waits for RabbitMQ confirmation.
Each dispatcher process has a unique owner identity, and every successful lease
increments an attempt number used as a fencing token. Publication and failure
updates require both the current owner and exact attempt, so a stale attempt
cannot overwrite a lease later reacquired by the same configured owner.
Only a positive confirmation allows one database transaction to set
`published_at` and move the job to `queued`. A crash after confirmation but
before that transaction may produce the same event again, so delivery remains
explicitly at least once. Waiting for a confirmation has an end-to-end
wall-clock deadline; an unknown outcome forcibly closes the broker transport
and leaves the event unpublished for retry. The future consumer must use
`eventId` idempotently.

The ML worker, API result-event consumer, and ML result updates remain outside
this focused increment.

## Layout

- `src/reactorfront_api/app.py`: HTTP composition and process probes
- `src/reactorfront_api/service.py`: application policy and compensation
- `src/reactorfront_api/persistence.py`: API-owned SQLAlchemy model and repository
- `src/reactorfront_api/storage.py`: S3-compatible object adapter
- `src/reactorfront_api/event_contracts.py`: canonical event validation
- `src/reactorfront_api/outbox.py`: dispatcher policy, retry, and orchestration
- `src/reactorfront_api/rabbitmq.py`: durable topology and confirmed publisher
- `src/reactorfront_api/outbox_main.py`: long-running and readiness process role
- `alembic/`: explicit database history
- `tests/`: unit tests and real-service integration proof

## Configuration

Runtime settings use the `PORTFOLIO_` prefix. Committed defaults are safe local
examples and are overridden inside Compose.

| Variable | Default |
|---|---|
| `PORTFOLIO_DATABASE_URL` | PostgreSQL on `127.0.0.1:55432` |
| `PORTFOLIO_S3_ENDPOINT_URL` | `http://127.0.0.1:59000` |
| `PORTFOLIO_S3_ACCESS_KEY_ID` | `portfolio-local-access` |
| `PORTFOLIO_S3_SECRET_ACCESS_KEY` | `portfolio-local-secret` |
| `PORTFOLIO_S3_BUCKET` | `portfolio-documents` |
| `PORTFOLIO_S3_REGION` | `us-east-1` |
| `PORTFOLIO_RABBITMQ_URL` | RabbitMQ on `127.0.0.1:55672` |
| `PORTFOLIO_RABBITMQ_TIMEOUT_SECONDS` | `5` |
| `PORTFOLIO_OUTBOX_BATCH_SIZE` | `8` |
| `PORTFOLIO_OUTBOX_LEASE_SECONDS` | `30` |
| `PORTFOLIO_OUTBOX_POLL_SECONDS` | `0.25` |
| `PORTFOLIO_OUTBOX_RETRY_BASE_SECONDS` | `1` |
| `PORTFOLIO_OUTBOX_RETRY_MAX_SECONDS` | `30` |

These values are development-only. Required host ports bind to `127.0.0.1`,
and the MinIO administration console is not published to the host.

## Verification

From the repository root:

```console
uv sync --project apps/api --frozen
python scripts/verify.py --static-only
```

GitHub Actions runs `python scripts/verify.py` without the flag. It builds the
fixed PostgreSQL, MinIO, and RabbitMQ environment, applies migrations, rejects
model drift, starts the API and outbox roles, and exercises the real HTTP,
database, object-storage, publisher-confirm, persistence, duplicate-delivery,
restart-recovery, stale-attempt fencing, and confirmation-deadline boundaries.

Authentication and authorization are deliberately deferred beyond the first
vertical slice.
