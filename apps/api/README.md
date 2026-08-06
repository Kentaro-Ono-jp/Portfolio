# API application boundary

## Responsibility

This area exposes the backend API and coordinates API-owned application use
cases. It accepts and validates PDFs, stores source objects, atomically records
a document, processing job, and transactional outbox event, dispatches the
committed event, and consumes ML result events through independently runnable
API image roles.

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
- PyJWT access-token validation with exact issuer, audience, algorithm, time,
  JWKS-cache, and API-owned capability policy
- bearer authorization on every document route, with stable-principal
  ownership filtering that deliberately returns the same `404` for an absent
  document and another principal's document
- API-owned OIDC and controlled-system principals with populated-v1 migration
- S3-compatible source-object storage through boto3
- authenticated source retrieval that checks persisted and object metadata,
  bounded size, and SHA-256 before returning a PDF
- owner-filtered review reads and one immutable approval or correction guarded
  by a strong entity tag and UUID idempotency key
- PostgreSQL-serialized review writes that atomically commit the terminal
  decision, idempotency receipt, and sanitized review audit event
- append-only submission, terminal-processing, and review audit history with
  deterministic ordering and duplicate-event suppression
- canonical JSON Schema validation before outbox persistence
- safe PostgreSQL outbox leasing with process-unique ownership, attempt fencing,
  and expired-lease recovery
- persistent RabbitMQ publication with mandatory routing, publisher confirms,
  and a wall-clock confirmation deadline
- Celery protocol v2-compatible requested-task envelopes
- at-least-once retry with bounded backoff and stable event identity
- atomic post-confirm outbox publication and `accepted` to `queued` transition
- manual-ack result-event consumption through the durable result queue
- strict `document.processing.completed.v2` lineage validation and atomic
  persistence, while admitted v1 history remains explicitly
  `legacy-unmeasured`
- read-only feedback-candidate projection for terminal synthetic reviews, with
  canonical output, corpus-inventory eligibility, measured lineage, aggregate
  sanitized omissions, and no automatic dataset or model mutation
- canonical result transport/schema/identity validation before persistence
- atomic result-event receipts and job-state transitions in PostgreSQL
- logical-event deduplication that tolerates a changed redelivery timestamp
- first-terminal-result preservation and poison-event rejection
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
and leaves the event unpublished for retry. The ML worker preserves `eventId`
as the stable requested-task identity across redelivery.

The independently deployable ML worker is implemented under `apps/ml` and uses
only the documented task and result-event contracts. The `api-events` role
validates AMQP metadata and canonical JSON Schema before it touches API-owned
state. A receipt keyed by `eventId` and an immutable logical-payload digest is
committed in the same transaction as the job mutation. The digest excludes
only `occurredAt`, because a legitimate at-least-once republication retains its
logical ID and business result while recording a new observation time.

Started events apply only after the outbox has moved the job to `queued`;
terminal events apply only after `processing`. A valid early event is requeued
with a bounded delay. Matching redelivery is acknowledged as a no-op, while
event-ID reuse, cross-identity input, impossible transitions, and conflicting
terminal results are rejected without mutation. The first committed terminal
result therefore remains authoritative.

## Layout

- `src/reactorfront_api/app.py`: HTTP composition and process probes
- `src/reactorfront_api/service.py`: application policy and compensation
- `src/reactorfront_api/persistence.py`: API-owned SQLAlchemy model and repository
- `src/reactorfront_api/storage.py`: S3-compatible object adapter
- `src/reactorfront_api/event_contracts.py`: canonical event validation
- `src/reactorfront_api/outbox.py`: dispatcher policy, retry, and orchestration
- `src/reactorfront_api/rabbitmq.py`: durable topology and confirmed publisher
- `src/reactorfront_api/outbox_main.py`: long-running and readiness process role
- `src/reactorfront_api/result_consumer.py`: result validation, acknowledgement policy,
  and durable consumer topology
- `src/reactorfront_api/events_main.py`: long-running result-consumer and readiness role
- `src/reactorfront_api/feedback_export.py`: canonical sanitized feedback projection
- `src/reactorfront_api/feedback_export_main.py`: bounded stdout-only export command
- `feedback/`: closed export schema and explicit repository-curation procedure
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
| `PORTFOLIO_EVENTS_PREFETCH_COUNT` | `1` |
| `PORTFOLIO_EVENTS_REQUEUE_DELAY_SECONDS` | `0.25` |
| `PORTFOLIO_EVENTS_RECONNECT_DELAY_SECONDS` | `1` |
| `PORTFOLIO_OIDC_ISSUER` | `http://127.0.0.1:5556/dex` |
| `PORTFOLIO_OIDC_DISCOVERY_URL` | loopback Dex discovery document |
| `PORTFOLIO_OIDC_JWKS_URL` | loopback Dex JWKS; Compose uses the internal backchannel |
| `PORTFOLIO_OIDC_AUDIENCE` | `reactorfront-api` |
| `PORTFOLIO_OIDC_ALLOWED_ALGORITHM` | `RS256` |
| `PORTFOLIO_OIDC_JWKS_CACHE_SECONDS` | `300` |
| `PORTFOLIO_OIDC_CLOCK_SKEW_SECONDS` | `30` |
| `PORTFOLIO_OIDC_HTTP_TIMEOUT_SECONDS` | `2` |
| `PORTFOLIO_OIDC_CAPABILITY_CLAIM` | `groups` |

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
model drift, starts the API, outbox, result-consumer, and ML worker roles, and
exercises the real HTTP, database, object-storage, publisher-confirm, result
persistence, duplicate-delivery, ordering-race, poison-input, restart-recovery,
stale-attempt fencing, and confirmation-deadline boundaries.

The populated-schema proof also migrates the principal foundation through the
review, idempotency, audit, and runtime-lineage schema. It preserves existing
documents, jobs, outbox events, principals, ownership, and result receipts and
does not fabricate historical lineage, review, or audit records. A lineage
migration downgrade is refused after measured evidence exists, because dropping
those columns would destroy accepted provenance.

All document operations require a validated bearer token and the mapped
`documents:submit` or `documents:read` capability. Submission persists the
resolved stable principal as owner. Status and source reads filter by that same
principal, so cross-owner probes do not reveal document existence. The Next.js
boundary owns the browser session and forwards access tokens only on the
server; health and readiness probes remain intentionally anonymous.

Review reads require `documents:read`, review writes require `reviews:write`,
and audit reads require `audit:read`; ownership remains mandatory for all
three. A completed machine result initially exposes an `unreviewed` entity tag
that includes every immutable lineage field in its identity.
The first successful write produces an immutable `approved` or `corrected`
decision. An identical idempotent replay returns that result, while conflicting
key reuse, stale evidence, cross-owner access, and a second terminal decision
cannot mutate it.

The feedback exporter is an offline API-area command rather than an HTTP
endpoint. It reads terminal review and measured result state in a PostgreSQL
read-only transaction, accepts one explicit canonical repository-owned
synthetic corpus inventory, and writes only the closed v1 export document to
standard output. Source bytes, filenames, actor identity, internal IDs,
timestamps, comments, database values, and object keys are excluded. Repeated
export over unchanged state and inventory is byte-identical. See
[the feedback export and curation procedure](feedback/README.md).
