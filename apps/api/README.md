# API application boundary

## Responsibility

This area exposes the backend API and coordinates API-owned application use
cases. The current increment accepts and validates PDFs, stores source objects,
and atomically records a document, processing job, and transactional outbox
event.

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
- stable public problem responses without raw internal errors
- pytest, Ruff, strict mypy, pip-audit, and branch-aware coverage

The API writes the source object first, then inserts the document, accepted job,
and requested outbox event in one database transaction. A failed transaction
triggers a best-effort object deletion. The submitted filename is display-only;
the server creates the object key and persists a SHA-256 digest.

The outbox dispatcher, RabbitMQ consumers, Celery worker, and ML result updates
are deliberately outside this focused increment.

## Layout

- `src/reactorfront_api/app.py`: HTTP composition and process probes
- `src/reactorfront_api/service.py`: application policy and compensation
- `src/reactorfront_api/persistence.py`: API-owned SQLAlchemy model and repository
- `src/reactorfront_api/storage.py`: S3-compatible object adapter
- `src/reactorfront_api/event_contracts.py`: canonical event validation
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

These values are development-only and grant no access outside the isolated
Compose project.

## Verification

From the repository root:

```console
uv sync --project apps/api --frozen
python scripts/verify.py --static-only
```

GitHub Actions runs `python scripts/verify.py` without the flag. It builds the
fixed PostgreSQL and MinIO environment, applies migrations, rejects model drift,
starts the API image, and exercises the real HTTP, database, and object-storage
boundaries.

Authentication and authorization are deliberately deferred beyond the first
vertical slice.
