# ML application boundary

## Responsibility

This independently deployable application consumes the canonical
`reactorfront_ml.process_document` Celery task, reads its source PDF from the
S3-compatible object store, verifies the recorded SHA-256, performs deterministic
CPU PyTorch classification, and publishes canonical processing result events.
It never imports API or Web internals and has no PostgreSQL dependency,
configuration, credential, or client driver.

## Supported boundary

- one synthetic, single-page PDF with extractable English text
- `invoice` or `report` classification with confidence from 0 through 1
- Unicode NFKC normalization, lowercase ASCII-alphanumeric tokenization, and a
  deterministic bag-of-words vector
- repository-owned synthetic training data and a fixed CPU build path
- PyTorch resolved only from the official CPU wheel index; the lock rejects
  CUDA, NVIDIA, and Triton runtime packages
- model artifact generation during the image build; generated artifacts remain
  outside normal Git history
- source-object retrieval through the documented S3-compatible API only
- late-acknowledged Celery consumption and confirmed at-least-once result
  publication through RabbitMQ

OCR, scanned or encrypted documents, empty text, multiple pages, images, GPU,
production model-quality claims, API result persistence, and Web behavior are
not supported in this boundary. See [`MODEL_CARD.md`](MODEL_CARD.md) for the
model identity, provenance, evaluation condition, checksum, intended use, and
limitations.

## Task and result transport

The worker accepts `document.processing.requested.v1` as the first positional
argument of the existing Celery protocol v2 envelope on the durable
`reactorfront.document-processing.requested.v1` queue. It validates the
canonical JSON Schema before touching storage or the model.

For a valid request, the worker confirms `document.processing.started.v1`
before inference and then confirms one logical `document.processing.completed.v1`
or `document.processing.failed.v1` terminal outcome. Result events use the
durable direct exchange `reactorfront.documents.v1` and durable queue
`reactorfront.document-processing.events.v1`. The future API-owned consumer is
deliberately absent.

Result messages are persistent, mandatory-routed, and subject to a bounded
wall-clock publisher-confirm outcome. The requested task is late-acknowledged;
an unconfirmed started or terminal event is requeued. A lost acknowledgement
can repeat inference and publication, so event IDs are derived deterministically
from the requested `eventId` and event type. This is at-least-once behavior and
does not claim exactly-once execution.

Celery control, health-probe, and gossip event queues are transient and
exclusive. Their lifetime is tied to one connection, avoiding RabbitMQ's
deprecated transient non-exclusive queue mode without changing the durable
requested/result queues.

Transient object-store failures use at most three application attempts. Missing
objects, digest mismatch, unsupported PDFs, empty text, and deterministic model
failures publish stable sanitized failure codes. Logs carry safe identifiers
but never credentials, document text, raw task bodies, or raw exception text.

## Layout

- `src/reactorfront_ml/celery_app.py`: task route, late acknowledgement, and retry policy
- `src/reactorfront_ml/processor.py`: source-integrity and processing orchestration
- `src/reactorfront_ml/pdf_processing.py`: single-page PDF text boundary
- `src/reactorfront_ml/model.py`: deterministic generation, verification, and inference
- `src/reactorfront_ml/rabbitmq.py`: durable result topology and confirmed publisher
- `src/reactorfront_ml/storage.py`: S3-compatible source adapter
- `src/reactorfront_ml/health.py`: model, MinIO, and RabbitMQ readiness
- `data/training.json`: repository-authored synthetic training inputs
- `model.expected.sha256`: reviewed artifact checksum
- `audit-requirements.txt`: normalized CPU-wheel advisory identity for pip-audit
- `tests/`: isolated unit and contract tests

## Configuration

Runtime settings use the `PORTFOLIO_ML_` prefix. Committed defaults are safe
local examples and Compose replaces them with service DNS names.

| Variable | Default |
|---|---|
| `PORTFOLIO_ML_S3_ENDPOINT_URL` | `http://127.0.0.1:59000` |
| `PORTFOLIO_ML_S3_ACCESS_KEY_ID` | `portfolio-local-access` |
| `PORTFOLIO_ML_S3_SECRET_ACCESS_KEY` | `portfolio-local-secret` |
| `PORTFOLIO_ML_S3_BUCKET` | `portfolio-documents` |
| `PORTFOLIO_ML_S3_REGION` | `us-east-1` |
| `PORTFOLIO_ML_RABBITMQ_URL` | RabbitMQ on `127.0.0.1:55672` |
| `PORTFOLIO_ML_RABBITMQ_TIMEOUT_SECONDS` | `5` |
| `PORTFOLIO_ML_MODEL_ARTIFACT_PATH` | `artifacts/model/model.json` |
| `PORTFOLIO_ML_MODEL_CHECKSUM_PATH` | `artifacts/model/model.sha256` |
| `PORTFOLIO_ML_EVENT_CONTRACT_DIRECTORY` | `packages/contracts/events` |

There is intentionally no database setting. The Compose service publishes no
host port and runs as numeric non-root user `10002`.

## Verification

Install the exact ML dependency set and run the non-container checks:

```console
uv sync --project apps/ml --frozen
uv run --project apps/ml python scripts/verify_ml_model.py
uv run --project apps/ml pytest apps/ml/tests --cov=reactorfront_ml --cov-branch
python scripts/verify.py --static-only
```

GitHub Actions is the authoritative runtime proof. The full canonical verifier
builds the non-root image, generates and checks the model inside that build,
uses the real API/outbox/MinIO/RabbitMQ path, performs real PDF extraction and
CPU PyTorch inference, verifies a stable digest-mismatch failure, exercises
duplicate delivery and RabbitMQ restart recovery, captures evidence, and always
tears down only the `reactorfront-portfolio` Compose project.
