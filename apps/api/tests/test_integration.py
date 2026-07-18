from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from uuid import UUID

import boto3
import httpx2 as httpx
import pytest
from botocore.config import Config
from mypy_boto3_s3 import S3Client
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import IntegrityError

from reactorfront_api.settings import Settings

pytestmark = pytest.mark.integration
PDF = b"%PDF-1.7\nReactorFront integration document"


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
    correlation_id = UUID("11111111-1111-4111-8111-111111111111")

    with httpx.Client(base_url=base_url, timeout=10) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/ready").json() == {"status": "ok"}
        accepted = client.post(
            "/api/v1/documents",
            files={"file": ("invoice.pdf", PDF, "application/pdf")},
            headers={"X-Correlation-ID": str(correlation_id)},
        )

        assert accepted.status_code == 202
        assert accepted.headers["X-Correlation-ID"] == str(correlation_id)
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
            headers={"X-Correlation-ID": str(correlation_id)},
        )
        assert current.status_code == 200
        assert current.json()["status"] == "accepted"

        invalid = client.post(
            "/api/v1/documents",
            files={"file": ("not-pdf.pdf", b"not a pdf", "application/pdf")},
        )
        assert invalid.status_code == 400
        assert invalid.json()["code"] == "INVALID_DOCUMENT"

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
