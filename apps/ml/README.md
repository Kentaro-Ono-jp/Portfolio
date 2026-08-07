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
production model-quality claims, direct API state access, and Web behavior are
not supported in this boundary. See [`MODEL_CARD.md`](MODEL_CARD.md) for the
model identity, provenance, evaluation condition, checksum, intended use, and
limitations. See [`MODEL_DEVELOPMENT.md`](MODEL_DEVELOPMENT.md) for the
feedback-candidate, curation, family-disjoint evaluation, promotion, rollback,
runtime-lineage, and immutable human-decision boundary with stable evidence
links.

## Task and result transport

The worker accepts `document.processing.requested.v1` as the first positional
argument of the existing Celery protocol v2 envelope on the durable
`reactorfront.document-processing.requested.v1` queue. It validates the
canonical JSON Schema before touching storage or the model.

For a valid request, the worker confirms `document.processing.started.v1`
before inference and then confirms one logical `document.processing.completed.v2`
or `document.processing.failed.v1` terminal outcome. A completed event carries
the accepted champion's immutable dataset, preprocessing, pipeline, artifact,
evaluation-policy, and evaluation-report identity. Result events use the
durable direct exchange `reactorfront.documents.v1` and durable queue
`reactorfront.document-processing.events.v1`. The separate API-owned
`api-events` role consumes that queue without importing ML implementation.
Worker startup derives the selected identity from the one canonical promotion
manifest, reconstructs its artifact, and validates the dataset, policy,
evaluation report, comparison, and runtime artifact before publishing any
measured evidence.

Result messages are persistent, mandatory-routed, and subject to a bounded
wall-clock publisher-confirm outcome. The requested task is late-acknowledged;
an unconfirmed started or terminal event is requeued. A lost acknowledgement
can repeat inference and publication, so event IDs are derived deterministically
from the requested `eventId` and event type. This is at-least-once behavior and
does not claim exactly-once execution.

Celery control and health-probe queues are transient and exclusive. Their
lifetime is tied to one connection, avoiding RabbitMQ's deprecated transient
non-exclusive queue mode. The single-purpose worker disables unused cluster
gossip and mingle bootsteps; event-receiver queues remain explicitly exclusive
if enabled later. None of this changes the durable requested/result queues.

Transient object-store failures use at most three application attempts. Missing
objects, digest mismatch, unsupported PDFs, empty text, and deterministic model
failures publish stable sanitized failure codes. Logs carry safe identifiers
but never credentials, document text, raw task bodies, or raw exception text.
If publishing a scheduled Celery retry fails, the worker records the stable
`RETRY_PUBLISH_FAILED` code and requeues the original requested message instead
of accepting Celery's non-requeueing publication failure default.

## Layout

- `src/reactorfront_ml/celery_app.py`: task route, late acknowledgement, and retry policy
- `src/reactorfront_ml/processor.py`: source-integrity and processing orchestration
- `src/reactorfront_ml/pdf_processing.py`: single-page PDF text boundary
- `src/reactorfront_ml/model.py`: deterministic generation, verification, and inference
- `src/reactorfront_ml/candidate.py`: snapshot-bound candidate generation and
  canonical build-lineage verification
- `src/reactorfront_ml/evaluation.py`: canonical snapshot validation, leakage guards,
  metrics, absolute and champion-relative gates, and report verification
- `src/reactorfront_ml/promotion.py`: canonical promotion/rollback selection,
  reviewed-evidence validation, and deterministic artifact reconstruction
- `src/reactorfront_ml/rabbitmq.py`: durable result topology and confirmed publisher
- `src/reactorfront_ml/storage.py`: S3-compatible source adapter
- `src/reactorfront_ml/health.py`: model, MinIO, and RabbitMQ readiness
- `data/training.json`: repository-authored synthetic training inputs
- `evaluation/corpus/v1/`: canonical 18-sample inventory, portable sources,
  fixed 12/2/4 train/validation/test assignment, and immutable snapshot
- `evaluation/policy-v1.json`: predeclared absolute and champion-relative
  quality gates, score treatment, completeness, and zero-drift policy
- `evaluation/evaluation-report-v1.schema.json`: closed machine-readable report
  contract shared by champion and future candidate evaluations
- `evaluation/champion-baseline-v1.json`: complete canonical held-out report for
  the previous checksum-verified champion and reviewed rollback identity
- `evaluation/candidate-build-v1.json`: reviewed candidate artifact identity,
  train-only membership, fixed seed, dependency lock, and no-calibration treatment
- `evaluation/candidate-report-v1.json`: complete canonical held-out report for
  the reproducible candidate
- `evaluation/candidate-comparison-v1.json`: independently recomputed absolute
  and champion-relative promotion-eligibility decision
- `evaluation/candidate-comparison-v1.schema.json`: closed comparison-report contract
- `evaluation/promoted-model-v1.json`: sole reviewed runtime model selection
- `evaluation/promoted-model-v1.schema.json`: closed promotion and rollback contract
- `MODEL_DEVELOPMENT.md`: bounded model-development and evidence summary
- `MODEL_CARD.md`: promoted model identity, intended use, evaluation, and limitations
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
| `PORTFOLIO_ML_PROMOTION_MANIFEST_PATH` | `apps/ml/evaluation/promoted-model-v1.json` |
| `PORTFOLIO_ML_PROMOTION_MANIFEST_SCHEMA_PATH` | `apps/ml/evaluation/promoted-model-v1.schema.json` |
| `PORTFOLIO_ML_EVENT_CONTRACT_DIRECTORY` | `packages/contracts/events` |

There is intentionally no database setting. The Compose service publishes no
host port and runs as numeric non-root user `10002`.

## Verification

Install the exact ML dependency set and run the non-container checks:

```console
uv sync --project apps/ml --frozen
uv run --project apps/ml python scripts/verify_ml_model.py
uv run --project apps/ml python scripts/verify_ml_evaluation.py
uv run --project apps/ml pytest apps/ml/tests --cov=reactorfront_ml --cov-branch
python scripts/verify.py --static-only
```

GitHub Actions is the authoritative runtime proof. The full canonical verifier
builds the non-root image, generates and checks the model inside that build,
uses the real API/outbox/MinIO/RabbitMQ path, performs real PDF extraction and
CPU PyTorch inference, verifies a stable digest-mismatch failure, exercises
duplicate delivery, RabbitMQ restart recovery, and original-message redelivery
after an injected retry-publication failure, captures evidence, and always tears
down only the `reactorfront-portfolio` Compose project.

## Versioned evaluation baseline

The repository-owned snapshot `reactorfront-synthetic-documents-v1` contains
18 English snippets across ten source/template families. Its fixed split has
12 training, two validation, and four held-out test samples; every split
contains both supported classes and no family crosses a split. Canonical
verification checks every source digest and rejects duplicate IDs or digests,
conflicting normalized labels, normalized content reused across splits,
unsafe or missing sources, and family leakage.

The previous `document-type-v1` champion remains reproducible. On the four
held-out synthetic samples it processes 4/4 without a sanitized failure and
records macro F1 `1.0`, invoice/report precision, recall, and F1 of `1.0`, and
mean true-label model score `0.99982216`. Its four sanitized accepted outcomes
are the atomic source for recomputing completeness, confusion, score quality,
metrics, and gates. The canonical report digest is
`1337d7bf0368799ebd2bc088cfda16544ca78c3ed77f96ba265a7d9b090a19b5`.
Two clean evaluations must be byte-identical to the committed baseline.

The snapshot-driven `document-type-candidate-v1` build consumes exactly the 12
declared training samples and records the dataset, split, preprocessing,
pipeline, fixed seed, `uv.lock`, training membership, and generated artifact
identity. Two clean builds produce artifact SHA-256
`17006d0e045fdc42547ca0b0dd058eb67532e6967a1136156c51e4cb4c00de09`.
The generated artifact remains outside normal Git history.

On the unchanged four-sample test split, the candidate also processes 4/4 with
macro F1 `1.0`, per-class recall `1.0`, and mean true-label model score
`0.99982216`. Its canonical report SHA-256 is
`83493ba1053c6252651e64a9afdb424385eb527c1c2ca94cbc99ade0d610d861`;
the independently recomputed comparison SHA-256 is
`92d8878c37a2c39a25f5d5241e54b1acaff7fbc2012d975d4b659f6fb72db041`.
All frozen absolute and champion-relative gates pass. The reviewed
`promoted-model-v1.json` now selects this exact candidate and binds its
artifact, dataset, preprocessing, pipeline, policy, report, comparison, and
task ontology. The image build generates only that selection; startup and
readiness reject a missing, noncanonical, mismatched, ineligible, or merely
newest artifact without fallback.

These figures describe only this tiny reviewed synthetic snapshot. The score
is not a calibrated probability, and the baseline makes no production
accuracy, fairness, privacy, robustness, or generalization claim. The promoted
model intentionally applies no confidence calibration.

Runtime lineage now describes `document-type-candidate-v1`. The same manifest
schema can select the previously accepted `document-type-v1` identity for a
reviewed rollback, while prior machine and human evidence remains immutable.
Neither promotion nor rollback turns review outcomes into training data.
