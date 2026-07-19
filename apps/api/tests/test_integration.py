from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import UUID

import boto3
import httpx2 as httpx
import pika
import pytest
from botocore.config import Config
from botocore.exceptions import ClientError
from mypy_boto3_s3 import S3Client
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from reactorfront_api.domain import (
    ProcessingStatus,
    PublicProblem,
    PublishFailureCode,
    PublishFinalizeResult,
)
from reactorfront_api.event_contracts import JsonSchemaEventValidator
from reactorfront_api.outbox import (
    DispatchCycleResult,
    DispatcherPolicy,
    OutboxDispatcher,
)
from reactorfront_api.persistence import (
    DocumentRow,
    OutboxEventRow,
    ProcessingJobRow,
    SqlAlchemyOutboxRepository,
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


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def engine(settings: Settings) -> Iterator[Engine]:
    database_engine = create_engine(settings.database_url)
    with database_engine.begin() as connection:
        connection.execute(
            text("TRUNCATE outbox_events, processing_jobs, documents RESTART IDENTITY CASCADE")
        )
    yield database_engine
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
    allowed_tables = {"documents", "processing_jobs", "outbox_events"}
    if table_name not in allowed_tables:
        raise ValueError(f"Unexpected table name: {table_name}")
    with engine.connect() as connection:
        return int(connection.execute(text(f"SELECT count(*) FROM {table_name}")).scalar_one())


def test_submission_crosses_real_http_postgres_and_s3_boundaries(
    settings: Settings,
    engine: Engine,
    s3: S3Client,
) -> None:
    base_url = os.environ.get("PORTFOLIO_API_BASE_URL", "http://127.0.0.1:58000")

    with httpx.Client(base_url=base_url, timeout=10) as client:
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
        document = connection.execute(
            text(
                "SELECT object_key, sha256, content_type, size_bytes "
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
    assert tuple(document) == (object_key, digest, "application/pdf", len(PDF))
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
    recovered = claim("dispatcher-c")
    assert len(recovered) == 1
    assert recovered[0].lease_owner == "dispatcher-c"
    assert recovered[0].attempt_count == 2


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
        )
        is PublishFinalizeResult.PUBLISHED
    )
    assert (
        repository.mark_published(
            event_id=EVENT_ID,
            lease_owner="dispatcher-b",
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

    status = SqlAlchemySubmissionRepository(engine=engine).get_status(DOCUMENT_ID)
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

    def declare_exchange_only(
        channel: pika.adapters.blocking_connection.BlockingChannel,
    ) -> None:
        channel.exchange_declare(
            exchange=REQUEST_EXCHANGE,
            exchange_type="direct",
            durable=True,
        )

    monkeypatch.setattr(publisher, "_declare_topology", declare_exchange_only)
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

    status = SqlAlchemySubmissionRepository(engine=engine).get_status(DOCUMENT_ID)
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
