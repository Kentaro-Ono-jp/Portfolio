from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid5

import boto3
import httpx2 as httpx
import pika
import pytest
from botocore.config import Config
from botocore.exceptions import ClientError
from mypy_boto3_s3 import S3Client
from scripts.oidc_test_client import obtain_access_token
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import reactorfront_api.rabbitmq as rabbitmq
from reactorfront_api.authentication import build_access_token_validator
from reactorfront_api.domain import (
    MeasuredModelEvidence,
    ProcessingStatus,
    PublicProblem,
    PublishFailureCode,
    PublishFinalizeResult,
    ResultApplyOutcome,
    ResultEvent,
    ResultEventFailureCode,
    ResultEventInvariantError,
    ResultEventType,
    ReviewCommand,
    ReviewOperationError,
    ReviewOperationFailureCode,
    ReviewRecord,
    ReviewStatus,
    review_entity_tag,
)
from reactorfront_api.event_contracts import JsonSchemaEventValidator
from reactorfront_api.feedback_export import FeedbackExporter
from reactorfront_api.outbox import (
    DispatchCycleResult,
    DispatcherPolicy,
    OutboxDispatcher,
)
from reactorfront_api.persistence import (
    API_SYSTEM_PRINCIPAL_ID,
    LEGACY_SYSTEM_PRINCIPAL_ID,
    DocumentRow,
    OutboxEventRow,
    PrincipalRow,
    ProcessingJobRow,
    ReviewDecisionRow,
    SqlAlchemyFeedbackExportRepository,
    SqlAlchemyOutboxRepository,
    SqlAlchemyPrincipalRepository,
    SqlAlchemyResultEventRepository,
    SqlAlchemySubmissionRepository,
)
from reactorfront_api.rabbitmq import (
    REQUEST_EXCHANGE,
    REQUEST_QUEUE,
    REQUEST_ROUTING_KEY,
    REQUEST_TASK_NAME,
    PikaOutboxPublisher,
)
from reactorfront_api.request_limits import MULTIPART_ENVELOPE_BYTES
from reactorfront_api.service import MAX_DOCUMENT_BYTES, DocumentService
from reactorfront_api.settings import Settings
from reactorfront_api.storage import S3ObjectStorage
from tests.openapi_contract import assert_openapi_response

pytestmark = pytest.mark.integration
PDF = b"%PDF-1.7\nReactorFront integration document"
CORRELATION_ID = UUID("11111111-1111-4111-8111-111111111111")
DOCUMENT_ID = UUID("22222222-2222-4222-8222-222222222222")
JOB_ID = UUID("33333333-3333-4333-8333-333333333333")
EVENT_ID = UUID("44444444-4444-4444-8444-444444444444")
NOW = datetime(2026, 7, 18, 9, 0, tzinfo=UTC)
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FEEDBACK_INVENTORY_PATH = REPOSITORY_ROOT / "apps/ml/evaluation/corpus/v1/corpus.json"


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def engine(settings: Settings) -> Iterator[Engine]:
    database_engine = create_engine(settings.database_url)
    truncate = text(
        "TRUNCATE result_event_receipts, outbox_events, processing_jobs, documents "
        "RESTART IDENTITY CASCADE"
    )
    try:
        with database_engine.begin() as connection:
            connection.execute(truncate)
            connection.execute(text("DELETE FROM principals WHERE kind = 'oidc'"))
        yield database_engine
    finally:
        with database_engine.begin() as connection:
            connection.execute(truncate)
            connection.execute(text("DELETE FROM principals WHERE kind = 'oidc'"))
        database_engine.dispose()


@pytest.fixture
def s3(settings: Settings) -> Iterator[S3Client]:
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    listed = client.list_objects_v2(Bucket=settings.s3_bucket)
    objects = [{"Key": item["Key"]} for item in listed.get("Contents", [])]
    if objects:
        client.delete_objects(Bucket=settings.s3_bucket, Delete={"Objects": objects})
    yield client


@pytest.fixture
def rabbitmq_channel(
    settings: Settings,
) -> Iterator[pika.adapters.blocking_connection.BlockingChannel]:
    connection = pika.BlockingConnection(
        pika.URLParameters(settings.rabbitmq_url.get_secret_value())
    )
    channel = connection.channel()
    channel.queue_declare(queue=REQUEST_QUEUE, durable=True)
    channel.queue_purge(queue=REQUEST_QUEUE)
    yield channel
    channel.queue_purge(queue=REQUEST_QUEUE)
    connection.close()


def table_count(engine: Engine, table_name: str) -> int:
    allowed_tables = {
        "documents",
        "processing_jobs",
        "outbox_events",
        "result_event_receipts",
        "principals",
        "review_decisions",
        "idempotency_records",
        "audit_events",
    }
    if table_name not in allowed_tables:
        raise ValueError(f"Unexpected table name: {table_name}")
    with engine.connect() as connection:
        return int(connection.execute(text(f"SELECT count(*) FROM {table_name}")).scalar_one())


def test_oidc_principal_resolution_is_stable_and_distinct_from_legacy(
    engine: Engine,
) -> None:
    repository = SqlAlchemyPrincipalRepository(engine=engine)

    first = repository.resolve_oidc_principal(
        issuer="http://127.0.0.1:5556/dex",
        subject="synthetic-reviewer",
    )
    repeated = repository.resolve_oidc_principal(
        issuer="http://127.0.0.1:5556/dex",
        subject="synthetic-reviewer",
    )

    assert first.principal_id == repeated.principal_id
    assert first.principal_id != LEGACY_SYSTEM_PRINCIPAL_ID
    assert table_count(engine, "principals") == 3
    with Session(engine) as session:
        legacy = session.get(PrincipalRow, LEGACY_SYSTEM_PRINCIPAL_ID)
        assert legacy is not None
        assert legacy.kind == "system"
        assert legacy.issuer is None
        assert legacy.subject is None
        api_system = session.get(PrincipalRow, API_SYSTEM_PRINCIPAL_ID)
        assert api_system is not None
        assert api_system.kind == "system"
        assert api_system.system_key == "api-processing"


def test_feedback_export_reads_terminal_measured_review_without_mutation(
    engine: Engine,
) -> None:
    inventory = json.loads(FEEDBACK_INVENTORY_PATH.read_bytes())
    eligible_source_sha256 = str(inventory["samples"][0]["sourceSha256"])
    private_filename = "private-feedback-source-name.pdf"
    private_object_key = "documents/private-feedback-object/source.pdf"
    document_id = UUID("90000000-0000-4000-8000-000000000001")
    job_id = UUID("90000000-0000-4000-8000-000000000002")
    review_id = UUID("90000000-0000-4000-8000-000000000003")
    with Session(engine) as session, session.begin():
        session.add(
            DocumentRow(
                id=document_id,
                submitted_by_principal_id=LEGACY_SYSTEM_PRINCIPAL_ID,
                original_filename=private_filename,
                object_key=private_object_key,
                sha256=eligible_source_sha256,
                content_type="application/pdf",
                size_bytes=123,
                created_at=NOW,
            )
        )
        session.flush()
        session.add(
            ProcessingJobRow(
                id=job_id,
                document_id=document_id,
                status="completed",
                attempt_count=1,
                model_version="document-type-v1",
                predicted_class="invoice",
                confidence=Decimal("0.9900"),
                dataset_version="reactorfront-synthetic-documents-v1",
                dataset_sha256="1" * 64,
                preprocessing_version="normalized-whitespace-v1",
                pipeline_version="document-classifier-v1",
                artifact_sha256="2" * 64,
                evaluation_policy_version="classification-evaluation-policy-v1",
                evaluation_policy_sha256="3" * 64,
                evaluation_report_sha256="4" * 64,
                failure_code=None,
                created_at=NOW,
                started_at=NOW,
                completed_at=NOW,
            )
        )
        session.flush()
        session.add(
            ReviewDecisionRow(
                id=review_id,
                document_id=document_id,
                job_id=job_id,
                reviewer_principal_id=LEGACY_SYSTEM_PRINCIPAL_ID,
                machine_classification="invoice",
                final_classification="report",
                status="corrected",
                review_version=1,
                decided_at=NOW,
            )
        )

    before = {
        table: table_count(engine, table)
        for table in (
            "documents",
            "processing_jobs",
            "review_decisions",
            "idempotency_records",
            "audit_events",
        )
    }
    repository = SqlAlchemyFeedbackExportRepository(engine=engine)
    rendered = FeedbackExporter(
        repository=repository,
        inventory_path=FEEDBACK_INVENTORY_PATH,
    ).export_bytes()
    after = {table: table_count(engine, table) for table in before}

    document = json.loads(rendered)
    assert before == after
    assert document["omissions"] == []
    assert document["candidates"] == [
        {
            "candidateId": document["candidates"][0]["candidateId"],
            "finalClassification": "report",
            "machineClassification": "invoice",
            "modelLineage": {
                "artifactSha256": "2" * 64,
                "datasetSha256": "1" * 64,
                "datasetVersion": "reactorfront-synthetic-documents-v1",
                "evaluationPolicySha256": "3" * 64,
                "evaluationPolicyVersion": "classification-evaluation-policy-v1",
                "evaluationReportSha256": "4" * 64,
                "modelVersion": "document-type-v1",
                "pipelineVersion": "document-classifier-v1",
                "preprocessingVersion": "normalized-whitespace-v1",
            },
            "reviewOutcome": "corrected",
            "sourceSha256": eligible_source_sha256,
        }
    ]
    assert private_filename.encode() not in rendered
    assert private_object_key.encode() not in rendered
    assert str(document_id).encode() not in rendered
    assert str(job_id).encode() not in rendered
    assert str(review_id).encode() not in rendered


def test_submission_crosses_real_http_postgres_and_s3_boundaries(
    settings: Settings,
    engine: Engine,
    s3: S3Client,
) -> None:
    base_url = os.environ.get("PORTFOLIO_API_BASE_URL", "http://127.0.0.1:58000")
    access_token, _identity_metadata = obtain_access_token(settings)
    authenticated_principal = build_access_token_validator(settings).validate(access_token)
    authorization = {"Authorization": f"Bearer {access_token}"}

    with httpx.Client(base_url=base_url, timeout=10, headers=authorization) as client:
        health = client.get("/health")
        readiness = client.get("/ready")
        assert health.json() == {"status": "ok"}
        assert readiness.json() == {"status": "ok"}
        assert_openapi_response(health, path="/health", method="get")
        assert_openapi_response(readiness, path="/ready", method="get")

        s3.delete_bucket(Bucket=settings.s3_bucket)
        try:
            unavailable = client.post(
                "/api/v1/documents",
                files={"file": ("invoice.pdf", PDF, "application/pdf")},
                headers={"X-Correlation-ID": str(CORRELATION_ID)},
            )
        finally:
            s3.create_bucket(Bucket=settings.s3_bucket)
        assert unavailable.status_code == 503
        assert_openapi_response(unavailable, path="/api/v1/documents", method="post")

        accepted = client.post(
            "/api/v1/documents",
            files={"file": ("invoice.pdf", PDF, "application/pdf")},
            headers={"X-Correlation-ID": str(CORRELATION_ID)},
        )

        assert accepted.status_code == 202
        assert_openapi_response(accepted, path="/api/v1/documents", method="post")
        assert accepted.headers["X-Correlation-ID"] == str(CORRELATION_ID)
        body = accepted.json()
        document_id = UUID(body["documentId"])
        job_id = UUID(body["jobId"])
        assert body == {
            "documentId": str(document_id),
            "jobId": str(job_id),
            "status": "accepted",
        }

        current = client.get(
            f"/api/v1/documents/{document_id}",
            headers={"X-Correlation-ID": str(CORRELATION_ID)},
        )
        assert current.status_code == 200
        assert_openapi_response(
            current,
            path="/api/v1/documents/{documentId}",
            method="get",
        )
        assert current.json()["status"] == "accepted"

        invalid = client.post(
            "/api/v1/documents",
            files={"file": ("not-pdf.pdf", b"not a pdf", "application/pdf")},
        )
        assert invalid.status_code == 400
        assert_openapi_response(invalid, path="/api/v1/documents", method="post")
        assert invalid.json()["code"] == "INVALID_DOCUMENT"

        unsupported = client.post(
            "/api/v1/documents",
            files={"file": ("image.png", b"not a PDF", "image/png")},
        )
        assert unsupported.status_code == 415
        assert_openapi_response(unsupported, path="/api/v1/documents", method="post")

        oversized = client.post(
            "/api/v1/documents",
            files={
                "file": (
                    "oversized.pdf",
                    b"%PDF-" + b"x" * (MAX_DOCUMENT_BYTES + MULTIPART_ENVELOPE_BYTES),
                    "application/pdf",
                )
            },
        )
        assert oversized.status_code == 413
        assert_openapi_response(oversized, path="/api/v1/documents", method="post")

        missing = client.get("/api/v1/documents/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        assert missing.status_code == 404
        assert_openapi_response(
            missing,
            path="/api/v1/documents/{documentId}",
            method="get",
        )

    assert table_count(engine, "documents") == 1
    assert table_count(engine, "processing_jobs") == 1
    assert table_count(engine, "outbox_events") == 1

    with engine.connect() as connection:
        authenticated_owner_id = connection.execute(
            text("SELECT id FROM principals WHERE issuer = :issuer AND subject = :subject"),
            {
                "issuer": authenticated_principal.issuer,
                "subject": authenticated_principal.subject,
            },
        ).scalar_one()
        document = connection.execute(
            text(
                "SELECT object_key, sha256, content_type, size_bytes, "
                "submitted_by_principal_id "
                "FROM documents WHERE id = :document_id"
            ),
            {"document_id": document_id},
        ).one()
        job = connection.execute(
            text("SELECT status, attempt_count FROM processing_jobs WHERE id = :job_id"),
            {"job_id": job_id},
        ).one()
        outbox = connection.execute(
            text(
                "SELECT event_type, aggregate_id, payload, published_at, attempt_count "
                "FROM outbox_events"
            )
        ).one()

    digest = hashlib.sha256(PDF).hexdigest()
    object_key = f"documents/{document_id}/source.pdf"
    assert tuple(document) == (
        object_key,
        digest,
        "application/pdf",
        len(PDF),
        authenticated_owner_id,
    )
    assert authenticated_owner_id != LEGACY_SYSTEM_PRINCIPAL_ID
    assert tuple(job) == ("accepted", 0)
    assert outbox.event_type == "document.processing.requested.v1"
    assert outbox.aggregate_id == job_id
    assert outbox.payload["documentId"] == str(document_id)
    assert outbox.payload["sourceSha256"] == digest
    assert outbox.published_at is None
    assert outbox.attempt_count == 0

    stored = s3.get_object(Bucket=settings.s3_bucket, Key=object_key)
    assert stored["Body"].read() == PDF
    assert stored["ContentType"] == "application/pdf"
    assert stored["Metadata"] == {"sha256": digest}

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text("UPDATE processing_jobs SET predicted_class = 'invoice' WHERE id = :job_id"),
            {"job_id": job_id},
        )


def test_real_postgres_failure_compensates_real_s3_object(
    settings: Settings,
    engine: Engine,
    s3: S3Client,
) -> None:
    conflict_document_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    conflict_job_id = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    with Session(engine) as session, session.begin():
        session.add(
            DocumentRow(
                id=conflict_document_id,
                submitted_by_principal_id=LEGACY_SYSTEM_PRINCIPAL_ID,
                original_filename="existing.pdf",
                object_key=f"documents/{conflict_document_id}/source.pdf",
                sha256="a" * 64,
                content_type="application/pdf",
                size_bytes=1,
                created_at=NOW,
            )
        )
        session.flush()
        session.add(
            ProcessingJobRow(
                id=conflict_job_id,
                document_id=conflict_document_id,
                status=ProcessingStatus.ACCEPTED.value,
                attempt_count=0,
                created_at=NOW,
            )
        )
        session.flush()
        session.add(
            OutboxEventRow(
                event_id=EVENT_ID,
                event_type="existing.v1",
                aggregate_id=conflict_job_id,
                payload={"existing": True},
                created_at=NOW,
                attempt_count=0,
            )
        )

    service = make_real_service(settings=settings, engine=engine, s3=s3)
    with pytest.raises(PublicProblem) as captured:
        service.submit(
            stream=BytesIO(PDF),
            original_filename="invoice.pdf",
            content_type="application/pdf",
            correlation_id=CORRELATION_ID,
            principal_id=LEGACY_SYSTEM_PRINCIPAL_ID,
        )

    assert captured.value.status == 503
    assert table_count(engine, "documents") == 1
    assert table_count(engine, "processing_jobs") == 1
    assert table_count(engine, "outbox_events") == 1
    with pytest.raises(ClientError) as missing_object:
        s3.head_object(
            Bucket=settings.s3_bucket,
            Key=f"documents/{DOCUMENT_ID}/source.pdf",
        )
    assert missing_object.value.response["Error"]["Code"] in {"404", "NoSuchKey"}


def test_commit_acknowledgement_loss_reconciles_real_postgres_and_keeps_source(
    settings: Settings,
    engine: Engine,
    s3: S3Client,
) -> None:
    acknowledgement_lost = False

    def lose_acknowledgement(_session: Session) -> None:
        nonlocal acknowledgement_lost
        if not acknowledgement_lost:
            acknowledgement_lost = True
            raise ConnectionError("simulated commit acknowledgement loss")

    event.listen(Session, "after_commit", lose_acknowledgement)
    service = make_real_service(settings=settings, engine=engine, s3=s3)
    try:
        result = service.submit(
            stream=BytesIO(PDF),
            original_filename="invoice.pdf",
            content_type="application/pdf",
            correlation_id=CORRELATION_ID,
            principal_id=LEGACY_SYSTEM_PRINCIPAL_ID,
        )
    finally:
        event.remove(Session, "after_commit", lose_acknowledgement)

    assert acknowledgement_lost
    assert result.document_id == DOCUMENT_ID
    assert result.job_id == JOB_ID
    assert result.status is ProcessingStatus.ACCEPTED
    assert table_count(engine, "documents") == 1
    assert table_count(engine, "processing_jobs") == 1
    assert table_count(engine, "outbox_events") == 1
    stored = s3.get_object(
        Bucket=settings.s3_bucket,
        Key=f"documents/{DOCUMENT_ID}/source.pdf",
    )
    assert stored["Body"].read() == PDF


def test_real_postgres_leases_once_and_recovers_expired_work(
    settings: Settings,
    engine: Engine,
    s3: S3Client,
) -> None:
    service = make_real_service(settings=settings, engine=engine, s3=s3)
    service.submit(
        stream=BytesIO(PDF),
        original_filename="invoice.pdf",
        content_type="application/pdf",
        correlation_id=CORRELATION_ID,
        principal_id=LEGACY_SYSTEM_PRINCIPAL_ID,
    )
    repository = SqlAlchemyOutboxRepository(engine=engine)

    def claim(owner: str) -> list[object]:
        return repository.lease_pending(
            lease_owner=owner,
            lease_duration=timedelta(seconds=30),
            batch_size=1,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(claim, ["dispatcher-a", "dispatcher-b"]))

    leased = [lease for owner_claims in claims for lease in owner_claims]
    assert len(leased) == 1
    assert leased[0].event_id == EVENT_ID
    assert leased[0].attempt_count == 1

    assert repository.record_failure(
        event_id=EVENT_ID,
        lease_owner=leased[0].lease_owner,
        attempt_count=leased[0].attempt_count,
        code=PublishFailureCode.BROKER_UNAVAILABLE,
        retry_delay=timedelta(seconds=30),
    )
    assert not claim("dispatcher-c")

    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE outbox_events "
                "SET leased_until = CURRENT_TIMESTAMP - INTERVAL '1 second' "
                "WHERE event_id = :event_id"
            ),
            {"event_id": EVENT_ID},
        )
    recovered = claim(leased[0].lease_owner)
    assert len(recovered) == 1
    assert recovered[0].lease_owner == leased[0].lease_owner
    assert recovered[0].attempt_count == 2

    with engine.connect() as connection:
        active_lease_before = connection.execute(
            text(
                "SELECT lease_owner, leased_until, attempt_count, last_error "
                "FROM outbox_events WHERE event_id = :event_id"
            ),
            {"event_id": EVENT_ID},
        ).one()
    assert (
        repository.mark_published(
            event_id=EVENT_ID,
            lease_owner=leased[0].lease_owner,
            attempt_count=leased[0].attempt_count,
        )
        is PublishFinalizeResult.LEASE_LOST
    )
    assert not repository.record_failure(
        event_id=EVENT_ID,
        lease_owner=leased[0].lease_owner,
        attempt_count=leased[0].attempt_count,
        code=PublishFailureCode.CONFIRM_TIMEOUT,
        retry_delay=timedelta(seconds=1),
    )
    with engine.connect() as connection:
        active_lease_after = connection.execute(
            text(
                "SELECT lease_owner, leased_until, attempt_count, last_error "
                "FROM outbox_events WHERE event_id = :event_id"
            ),
            {"event_id": EVENT_ID},
        ).one()
    assert tuple(active_lease_after) == tuple(active_lease_before)


def test_real_rabbitmq_confirm_duplicate_and_atomic_queued_transition(
    settings: Settings,
    engine: Engine,
    s3: S3Client,
    rabbitmq_channel: pika.adapters.blocking_connection.BlockingChannel,
) -> None:
    service = make_real_service(settings=settings, engine=engine, s3=s3)
    service.submit(
        stream=BytesIO(PDF),
        original_filename="invoice.pdf",
        content_type="application/pdf",
        correlation_id=CORRELATION_ID,
        principal_id=LEGACY_SYSTEM_PRINCIPAL_ID,
    )
    repository = SqlAlchemyOutboxRepository(engine=engine)
    publisher = PikaOutboxPublisher(
        broker_url=settings.rabbitmq_url.get_secret_value(),
        timeout_seconds=settings.rabbitmq_timeout_seconds,
    )

    first = repository.lease_pending(
        lease_owner="dispatcher-a",
        lease_duration=timedelta(seconds=30),
        batch_size=1,
    )[0]
    publisher.publish(first)

    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE outbox_events "
                "SET leased_until = CURRENT_TIMESTAMP - INTERVAL '1 second' "
                "WHERE event_id = :event_id"
            ),
            {"event_id": EVENT_ID},
        )
    retry = repository.lease_pending(
        lease_owner="dispatcher-b",
        lease_duration=timedelta(seconds=30),
        batch_size=1,
    )[0]
    publisher.publish(retry)
    assert (
        repository.mark_published(
            event_id=EVENT_ID,
            lease_owner="dispatcher-b",
            attempt_count=retry.attempt_count,
        )
        is PublishFinalizeResult.PUBLISHED
    )
    assert (
        repository.mark_published(
            event_id=EVENT_ID,
            lease_owner="dispatcher-b",
            attempt_count=retry.attempt_count,
        )
        is PublishFinalizeResult.ALREADY_PUBLISHED
    )

    deliveries: list[tuple[pika.spec.Basic.Deliver, pika.BasicProperties, bytes]] = []
    for _ in range(2):
        method, properties, body = rabbitmq_channel.basic_get(
            queue=REQUEST_QUEUE,
            auto_ack=False,
        )
        assert method is not None
        assert properties is not None
        assert body is not None
        deliveries.append((method, properties, body))
        rabbitmq_channel.basic_ack(delivery_tag=method.delivery_tag)

    assert {item[1].message_id for item in deliveries} == {str(EVENT_ID)}
    for _method, properties, body in deliveries:
        assert properties.delivery_mode == 2
        assert properties.headers["task"] == REQUEST_TASK_NAME
        assert properties.headers["root_id"] == str(CORRELATION_ID)
        task_body = json.loads(body)
        assert task_body[0][0]["eventType"] == REQUEST_ROUTING_KEY
        assert task_body[0][0]["eventId"] == str(EVENT_ID)

    status = SqlAlchemySubmissionRepository(engine=engine).get_status(
        DOCUMENT_ID, LEGACY_SYSTEM_PRINCIPAL_ID
    )
    assert status is not None
    assert status.status is ProcessingStatus.QUEUED
    with engine.connect() as connection:
        persisted = connection.execute(
            text(
                "SELECT published_at, lease_owner, leased_until, attempt_count, last_error "
                "FROM outbox_events WHERE event_id = :event_id"
            ),
            {"event_id": EVENT_ID},
        ).one()
    assert persisted.published_at is not None
    assert persisted.lease_owner is None
    assert persisted.leased_until is None
    assert persisted.attempt_count == 2
    assert persisted.last_error is None


def test_real_confirm_deadline_returns_and_keeps_job_accepted(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    engine: Engine,
    s3: S3Client,
    rabbitmq_channel: pika.adapters.blocking_connection.BlockingChannel,
) -> None:
    del rabbitmq_channel
    service = make_real_service(settings=settings, engine=engine, s3=s3)
    service.submit(
        stream=BytesIO(PDF),
        original_filename="invoice.pdf",
        content_type="application/pdf",
        correlation_id=CORRELATION_ID,
        principal_id=LEGACY_SYSTEM_PRINCIPAL_ID,
    )
    original_confirm_delivery = pika.channel.Channel.confirm_delivery

    def suppress_delivery_confirmation(
        channel: pika.channel.Channel,
        _ack_nack_callback: Callable[
            [pika.frame.Method[pika.spec.Basic.Ack | pika.spec.Basic.Nack]],
            object,
        ],
        callback: Callable[[pika.frame.Method[pika.spec.Confirm.SelectOk]], object] | None = None,
    ) -> None:
        original_confirm_delivery(channel, lambda _frame: None, callback)

    monkeypatch.setattr(
        pika.channel.Channel,
        "confirm_delivery",
        suppress_delivery_confirmation,
    )
    repository = SqlAlchemyOutboxRepository(engine=engine)
    publisher = PikaOutboxPublisher(
        broker_url=settings.rabbitmq_url.get_secret_value(),
        timeout_seconds=1.0,
    )
    dispatcher = OutboxDispatcher(
        repository=repository,
        publisher=publisher,
        lease_owner="dispatcher-confirm-timeout-test",
        policy=DispatcherPolicy(
            batch_size=1,
            lease_duration=timedelta(seconds=5),
            poll_seconds=0.1,
            retry_base_seconds=1,
            retry_max_seconds=30,
        ),
    )
    started = time.monotonic()
    try:
        assert dispatcher.dispatch_once() is DispatchCycleResult.RETRY_SCHEDULED
        elapsed = time.monotonic() - started
        assert 0.8 <= elapsed <= 1.75

        status = SqlAlchemySubmissionRepository(engine=engine).get_status(
            DOCUMENT_ID, LEGACY_SYSTEM_PRINCIPAL_ID
        )
        assert status is not None
        assert status.status is ProcessingStatus.ACCEPTED
        with engine.connect() as connection:
            persisted = connection.execute(
                text(
                    "SELECT published_at, attempt_count, last_error "
                    "FROM outbox_events WHERE event_id = :event_id"
                ),
                {"event_id": EVENT_ID},
            ).one()
        assert persisted.published_at is None
        assert persisted.attempt_count == 1
        assert persisted.last_error == PublishFailureCode.CONFIRM_TIMEOUT.value
    finally:
        dispatcher.close()


def test_real_unroutable_publish_stays_accepted_and_records_retry(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    engine: Engine,
    s3: S3Client,
    rabbitmq_channel: pika.adapters.blocking_connection.BlockingChannel,
) -> None:
    service = make_real_service(settings=settings, engine=engine, s3=s3)
    service.submit(
        stream=BytesIO(PDF),
        original_filename="invoice.pdf",
        content_type="application/pdf",
        correlation_id=CORRELATION_ID,
        principal_id=LEGACY_SYSTEM_PRINCIPAL_ID,
    )
    repository = SqlAlchemyOutboxRepository(engine=engine)
    publisher = PikaOutboxPublisher(
        broker_url=settings.rabbitmq_url.get_secret_value(),
        timeout_seconds=settings.rabbitmq_timeout_seconds,
    )
    rabbitmq_channel.exchange_declare(
        exchange=REQUEST_EXCHANGE,
        exchange_type="direct",
        durable=True,
    )
    rabbitmq_channel.queue_bind(
        queue=REQUEST_QUEUE,
        exchange=REQUEST_EXCHANGE,
        routing_key=REQUEST_ROUTING_KEY,
    )
    rabbitmq_channel.queue_unbind(
        queue=REQUEST_QUEUE,
        exchange=REQUEST_EXCHANGE,
        routing_key=REQUEST_ROUTING_KEY,
    )

    def skip_queue_binding(
        attempt: rabbitmq._PublishAttempt,
        _frame: pika.frame.Method[pika.spec.Queue.DeclareOk],
    ) -> None:
        attempt._on_queue_bound(pika.frame.Method(1, pika.spec.Queue.BindOk()))

    monkeypatch.setattr(rabbitmq._PublishAttempt, "_on_queue_declared", skip_queue_binding)
    dispatcher = OutboxDispatcher(
        repository=repository,
        publisher=publisher,
        lease_owner="dispatcher-unroutable-test",
        policy=DispatcherPolicy(
            batch_size=1,
            lease_duration=timedelta(seconds=30),
            poll_seconds=0.1,
            retry_base_seconds=1,
            retry_max_seconds=30,
        ),
    )
    try:
        assert dispatcher.dispatch_once() is DispatchCycleResult.RETRY_SCHEDULED
    finally:
        rabbitmq_channel.queue_bind(
            queue=REQUEST_QUEUE,
            exchange=REQUEST_EXCHANGE,
            routing_key=REQUEST_ROUTING_KEY,
        )

    status = SqlAlchemySubmissionRepository(engine=engine).get_status(
        DOCUMENT_ID, LEGACY_SYSTEM_PRINCIPAL_ID
    )
    assert status is not None
    assert status.status is ProcessingStatus.ACCEPTED
    with engine.connect() as connection:
        persisted = connection.execute(
            text(
                "SELECT published_at, attempt_count, last_error "
                "FROM outbox_events WHERE event_id = :event_id"
            ),
            {"event_id": EVENT_ID},
        ).one()
    assert persisted.published_at is None
    assert persisted.attempt_count == 1
    assert persisted.last_error == PublishFailureCode.UNROUTABLE.value


def make_real_service(*, settings: Settings, engine: Engine, s3: S3Client) -> DocumentService:
    generated_ids = iter((DOCUMENT_ID, JOB_ID, EVENT_ID))
    return DocumentService(
        repository=SqlAlchemySubmissionRepository(engine=engine),
        object_storage=S3ObjectStorage(client=s3, bucket=settings.s3_bucket),
        event_validator=JsonSchemaEventValidator(
            contract_directory=settings.event_contract_directory
        ),
        id_factory=lambda: next(generated_ids),
        clock=lambda: NOW,
    )


def integration_result_event(
    event_type: ResultEventType,
    *,
    occurred_at: datetime,
) -> ResultEvent:
    is_completed = event_type.is_completed
    model_evidence = (
        MeasuredModelEvidence(
            dataset_version="reactorfront-synthetic-documents-v1",
            dataset_sha256="4" * 64,
            preprocessing_version="document-text-v1",
            pipeline_version="tfidf-logreg-v1",
            artifact_sha256="5" * 64,
            evaluation_policy_version="champion-baseline-v1",
            evaluation_policy_sha256="6" * 64,
            evaluation_report_sha256="7" * 64,
        )
        if event_type is ResultEventType.COMPLETED_V2
        else None
    )
    return ResultEvent(
        event_id=uuid5(EVENT_ID, event_type.value),
        event_type=event_type,
        occurred_at=occurred_at,
        correlation_id=CORRELATION_ID,
        document_id=DOCUMENT_ID,
        job_id=JOB_ID,
        object_key=f"documents/{DOCUMENT_ID}/source.pdf",
        source_sha256=hashlib.sha256(PDF).hexdigest(),
        model_version="document-type-v1",
        logical_payload_sha256={
            ResultEventType.STARTED: "1" * 64,
            ResultEventType.COMPLETED: "2" * 64,
            ResultEventType.COMPLETED_V2: "4" * 64,
            ResultEventType.FAILED: "3" * 64,
        }[event_type],
        model_evidence=model_evidence,
        classification="invoice" if is_completed else None,
        confidence=0.9876 if is_completed else None,
        failure_code="SOURCE_DIGEST_MISMATCH" if event_type is ResultEventType.FAILED else None,
    )


def seed_queued_integration_job(
    *,
    settings: Settings,
    engine: Engine,
    s3: S3Client,
) -> None:
    service = make_real_service(settings=settings, engine=engine, s3=s3)
    service.submit(
        stream=BytesIO(PDF),
        original_filename="invoice.pdf",
        content_type="application/pdf",
        correlation_id=CORRELATION_ID,
        principal_id=LEGACY_SYSTEM_PRINCIPAL_ID,
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE outbox_events SET published_at = CURRENT_TIMESTAMP "
                "WHERE event_id = :event_id"
            ),
            {"event_id": EVENT_ID},
        )
        connection.execute(
            text("UPDATE processing_jobs SET status = 'queued' WHERE id = :job_id"),
            {"job_id": JOB_ID},
        )


def test_result_events_commit_idempotently_and_preserve_first_terminal_state(
    settings: Settings,
    engine: Engine,
    s3: S3Client,
) -> None:
    seed_queued_integration_job(settings=settings, engine=engine, s3=s3)
    repository = SqlAlchemyResultEventRepository(engine=engine)
    started = integration_result_event(ResultEventType.STARTED, occurred_at=NOW)
    completed = integration_result_event(
        ResultEventType.COMPLETED_V2,
        occurred_at=NOW + timedelta(seconds=1),
    )

    assert repository.apply(started) is ResultApplyOutcome.APPLIED
    assert (
        repository.apply(replace(started, occurred_at=NOW + timedelta(milliseconds=10)))
        is ResultApplyOutcome.DUPLICATE
    )
    assert repository.apply(completed) is ResultApplyOutcome.APPLIED
    assert repository.apply(completed) is ResultApplyOutcome.DUPLICATE

    failed = integration_result_event(
        ResultEventType.FAILED,
        occurred_at=NOW + timedelta(seconds=2),
    )
    with pytest.raises(ResultEventInvariantError) as captured:
        repository.apply(failed)
    assert captured.value.code is ResultEventFailureCode.TERMINAL_CONFLICT

    status = SqlAlchemySubmissionRepository(engine=engine).get_status(
        DOCUMENT_ID, LEGACY_SYSTEM_PRINCIPAL_ID
    )
    assert status is not None
    assert status.status is ProcessingStatus.COMPLETED
    assert status.predicted_class == "invoice"
    assert status.confidence == pytest.approx(0.9876)
    assert status.model_version == "document-type-v1"
    assert status.model_evidence == completed.model_evidence
    assert status.failure_code is None
    history = SqlAlchemySubmissionRepository(engine=engine).get_audit_history(
        DOCUMENT_ID, LEGACY_SYSTEM_PRINCIPAL_ID
    )
    assert history is not None
    completion = history.events[-1]
    assert completion.action.value == "processing.completed"
    assert completion.details_version == 2
    assert completion.details == {
        "modelEvidenceStatus": "measured",
        "modelVersion": "document-type-v1",
        "datasetVersion": "reactorfront-synthetic-documents-v1",
        "datasetSha256": "4" * 64,
        "preprocessingVersion": "document-text-v1",
        "pipelineVersion": "tfidf-logreg-v1",
        "artifactSha256": "5" * 64,
        "evaluationPolicyVersion": "champion-baseline-v1",
        "evaluationPolicySha256": "6" * 64,
        "evaluationReportSha256": "7" * 64,
    }
    assert table_count(engine, "result_event_receipts") == 2


def test_result_event_transaction_rolls_back_receipt_and_invalid_result(
    settings: Settings,
    engine: Engine,
    s3: S3Client,
) -> None:
    seed_queued_integration_job(settings=settings, engine=engine, s3=s3)
    repository = SqlAlchemyResultEventRepository(engine=engine)
    started = integration_result_event(ResultEventType.STARTED, occurred_at=NOW)
    assert repository.apply(started) is ResultApplyOutcome.APPLIED

    invalid = replace(
        integration_result_event(
            ResultEventType.COMPLETED,
            occurred_at=NOW + timedelta(seconds=1),
        ),
        classification="memo",
    )
    with pytest.raises(IntegrityError):
        repository.apply(invalid)

    status = SqlAlchemySubmissionRepository(engine=engine).get_status(
        DOCUMENT_ID, LEGACY_SYSTEM_PRINCIPAL_ID
    )
    assert status is not None
    assert status.status is ProcessingStatus.PROCESSING
    assert status.predicted_class is None
    assert table_count(engine, "result_event_receipts") == 1


def test_review_concurrency_idempotency_and_audit_history_use_one_winner(
    settings: Settings,
    engine: Engine,
    s3: S3Client,
) -> None:
    seed_queued_integration_job(settings=settings, engine=engine, s3=s3)
    result_repository = SqlAlchemyResultEventRepository(engine=engine)
    assert (
        result_repository.apply(integration_result_event(ResultEventType.STARTED, occurred_at=NOW))
        is ResultApplyOutcome.APPLIED
    )
    assert (
        result_repository.apply(
            integration_result_event(
                ResultEventType.COMPLETED,
                occurred_at=NOW + timedelta(seconds=1),
            )
        )
        is ResultApplyOutcome.APPLIED
    )

    repository = SqlAlchemySubmissionRepository(engine=engine)
    current = repository.get_review(DOCUMENT_ID, LEGACY_SYSTEM_PRINCIPAL_ID)
    assert current is not None
    assert current.status is ReviewStatus.UNREVIEWED
    current_tag = review_entity_tag(current)
    commands = [
        ReviewCommand(
            document_id=DOCUMENT_ID,
            principal_id=LEGACY_SYSTEM_PRINCIPAL_ID,
            correlation_id=CORRELATION_ID,
            final_classification=final_classification,
            if_match=current_tag,
            idempotency_key=idempotency_key,
            request_digest=hashlib.sha256(
                json.dumps(
                    {"finalClassification": final_classification},
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode()
            ).hexdigest(),
            decision_id=decision_id,
            decided_at=NOW + timedelta(seconds=2),
        )
        for final_classification, idempotency_key, decision_id in (
            (
                "invoice",
                UUID("55555555-5555-4555-8555-555555555555"),
                UUID("66666666-6666-4666-8666-666666666666"),
            ),
            (
                "report",
                UUID("77777777-7777-4777-8777-777777777777"),
                UUID("88888888-8888-4888-8888-888888888888"),
            ),
        )
    ]

    def commit_review(
        command: ReviewCommand,
    ) -> tuple[ReviewCommand, object]:
        try:
            return command, repository.submit_review(command)
        except ReviewOperationError as error:
            return command, error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(commit_review, commands))

    winners = [
        (command, outcome)
        for command, outcome in outcomes
        if not isinstance(outcome, ReviewOperationFailureCode)
    ]
    losers = [
        outcome for _command, outcome in outcomes if isinstance(outcome, ReviewOperationFailureCode)
    ]
    assert len(winners) == 1
    assert losers == [ReviewOperationFailureCode.PRECONDITION_FAILED]
    winning_command, winning_record = winners[0]
    assert isinstance(winning_record, ReviewRecord)
    assert repository.submit_review(winning_command) == winning_record

    conflicting_replay = replace(
        winning_command,
        final_classification=(
            "report" if winning_command.final_classification == "invoice" else "invoice"
        ),
        request_digest="f" * 64,
        decision_id=UUID("99999999-9999-4999-8999-999999999999"),
    )
    with pytest.raises(ReviewOperationError) as captured:
        repository.submit_review(conflicting_replay)
    assert captured.value.code is ReviewOperationFailureCode.IDEMPOTENCY_CONFLICT

    hidden_document_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    with Session(engine) as session, session.begin():
        session.add(
            DocumentRow(
                id=hidden_document_id,
                submitted_by_principal_id=API_SYSTEM_PRINCIPAL_ID,
                original_filename="hidden.pdf",
                object_key=f"documents/{hidden_document_id}/source.pdf",
                sha256="a" * 64,
                content_type="application/pdf",
                size_bytes=1,
                created_at=NOW,
            )
        )
    hidden_target_reuse = replace(
        winning_command,
        document_id=hidden_document_id,
        decision_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaab"),
    )
    hidden_target_fresh = replace(
        hidden_target_reuse,
        idempotency_key=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaac"),
        decision_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaad"),
    )
    hidden_results: list[ReviewOperationFailureCode] = []
    for hidden_command in (hidden_target_reuse, hidden_target_fresh):
        with pytest.raises(ReviewOperationError) as captured:
            repository.submit_review(hidden_command)
        hidden_results.append(captured.value.code)
    assert hidden_results == [
        ReviewOperationFailureCode.DOCUMENT_NOT_FOUND,
        ReviewOperationFailureCode.DOCUMENT_NOT_FOUND,
    ]

    assert table_count(engine, "review_decisions") == 1
    assert table_count(engine, "idempotency_records") == 1
    assert table_count(engine, "audit_events") == 3
    history = repository.get_audit_history(DOCUMENT_ID, LEGACY_SYSTEM_PRINCIPAL_ID)
    assert history is not None
    assert [event.action.value for event in history.events] == [
        "document.submitted",
        "processing.completed",
        f"review.{winning_record.status.value}",
    ]

    machine = repository.get_status(DOCUMENT_ID, LEGACY_SYSTEM_PRINCIPAL_ID)
    assert machine is not None
    assert machine.predicted_class == "invoice"
    assert machine.confidence == pytest.approx(0.9876)
    assert machine.model_version == "document-type-v1"


def test_review_audit_insert_failure_rolls_back_decision_and_receipt(
    settings: Settings,
    engine: Engine,
    s3: S3Client,
) -> None:
    seed_queued_integration_job(settings=settings, engine=engine, s3=s3)
    result_repository = SqlAlchemyResultEventRepository(engine=engine)
    assert (
        result_repository.apply(integration_result_event(ResultEventType.STARTED, occurred_at=NOW))
        is ResultApplyOutcome.APPLIED
    )
    assert (
        result_repository.apply(
            integration_result_event(
                ResultEventType.COMPLETED,
                occurred_at=NOW + timedelta(seconds=1),
            )
        )
        is ResultApplyOutcome.APPLIED
    )
    repository = SqlAlchemySubmissionRepository(engine=engine)
    current = repository.get_review(DOCUMENT_ID, LEGACY_SYSTEM_PRINCIPAL_ID)
    assert current is not None
    command = ReviewCommand(
        document_id=DOCUMENT_ID,
        principal_id=LEGACY_SYSTEM_PRINCIPAL_ID,
        correlation_id=CORRELATION_ID,
        final_classification="invoice",
        if_match=review_entity_tag(current),
        idempotency_key=UUID("55555555-5555-4555-8555-555555555555"),
        request_digest="a" * 64,
        decision_id=UUID("66666666-6666-4666-8666-666666666666"),
        decided_at=NOW + timedelta(seconds=2),
    )
    audit_count_before = table_count(engine, "audit_events")

    def reject_review_audit(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        if statement.startswith("INSERT INTO audit_events"):
            raise RuntimeError("simulated audit persistence failure")

    event.listen(engine, "before_cursor_execute", reject_review_audit)
    try:
        with pytest.raises(RuntimeError, match="simulated audit persistence failure"):
            repository.submit_review(command)
    finally:
        event.remove(engine, "before_cursor_execute", reject_review_audit)

    assert table_count(engine, "review_decisions") == 0
    assert table_count(engine, "idempotency_records") == 0
    assert table_count(engine, "audit_events") == audit_count_before
    assert repository.get_review(DOCUMENT_ID, LEGACY_SYSTEM_PRINCIPAL_ID) == current
