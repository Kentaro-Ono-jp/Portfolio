from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from reactorfront_api.app import CORRELATION_HEADER, create_app
from reactorfront_api.domain import DocumentStatusRecord, ProcessingStatus
from reactorfront_api.request_limits import MULTIPART_ENVELOPE_BYTES
from reactorfront_api.service import MAX_DOCUMENT_BYTES, DocumentService
from tests.fakes import FakeRepository, FakeStorage, FakeValidator
from tests.openapi_contract import assert_openapi_response

CORRELATION_ID = UUID("11111111-1111-4111-8111-111111111111")
DOCUMENT_ID = UUID("22222222-2222-4222-8222-222222222222")
JOB_ID = UUID("33333333-3333-4333-8333-333333333333")
EVENT_ID = UUID("44444444-4444-4444-8444-444444444444")
NOW = datetime(2026, 7, 18, 9, 0, tzinfo=UTC)


def make_client(
    *,
    repository: FakeRepository | None = None,
    storage: FakeStorage | None = None,
) -> tuple[TestClient, FakeRepository, FakeStorage]:
    selected_repository = repository or FakeRepository()
    selected_storage = storage or FakeStorage()
    ids = iter((DOCUMENT_ID, JOB_ID, EVENT_ID))
    service = DocumentService(
        repository=selected_repository,
        object_storage=selected_storage,
        event_validator=FakeValidator(),
        id_factory=lambda: next(ids),
        clock=lambda: NOW,
    )
    return TestClient(create_app(service=service)), selected_repository, selected_storage


def test_document_submission_and_lookup_preserve_correlation_id() -> None:
    client, repository, storage = make_client()

    with client:
        accepted = client.post(
            "/api/v1/documents",
            files={"file": ("invoice.pdf", b"%PDF-1.7\ntest", "application/pdf")},
            headers={CORRELATION_HEADER: str(CORRELATION_ID)},
        )
        current = client.get(
            f"/api/v1/documents/{DOCUMENT_ID}",
            headers={CORRELATION_HEADER: str(CORRELATION_ID)},
        )

    assert accepted.status_code == 202
    assert_openapi_response(accepted, path="/api/v1/documents", method="post")
    assert accepted.headers[CORRELATION_HEADER] == str(CORRELATION_ID)
    assert accepted.json() == {
        "documentId": str(DOCUMENT_ID),
        "jobId": str(JOB_ID),
        "status": "accepted",
    }
    assert current.status_code == 200
    assert_openapi_response(
        current,
        path="/api/v1/documents/{documentId}",
        method="get",
    )
    assert current.headers[CORRELATION_HEADER] == str(CORRELATION_ID)
    assert current.json() == {
        "documentId": str(DOCUMENT_ID),
        "jobId": str(JOB_ID),
        "status": "accepted",
        "createdAt": "2026-07-18T09:00:00Z",
    }
    assert len(repository.submissions) == 1
    assert len(storage.objects) == 1


def test_public_problems_are_stable_and_do_not_leak_internal_details() -> None:
    repository = FakeRepository(save_error=RuntimeError("postgres password leaked"))
    client, _repository, _storage = make_client(repository=repository)

    with client:
        response = client.post(
            "/api/v1/documents",
            files={"file": ("invoice.pdf", b"%PDF-1.7\ntest", "application/pdf")},
            headers={CORRELATION_HEADER: str(CORRELATION_ID)},
        )

    assert response.status_code == 503
    assert_openapi_response(response, path="/api/v1/documents", method="post")
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.headers[CORRELATION_HEADER] == str(CORRELATION_ID)
    assert response.json() == {
        "type": "urn:reactorfront:problem:dependency-unavailable",
        "title": "Dependency unavailable",
        "status": 503,
        "detail": "A required service is temporarily unavailable.",
        "code": "DEPENDENCY_UNAVAILABLE",
        "correlationId": str(CORRELATION_ID),
    }
    assert "password" not in response.text


def test_invalid_document_and_unknown_document_match_contract() -> None:
    client, _repository, _storage = make_client()

    with client:
        invalid = client.post(
            "/api/v1/documents",
            files={"file": ("invoice.pdf", b"not a pdf", "application/pdf")},
            headers={CORRELATION_HEADER: str(CORRELATION_ID)},
        )
        missing = client.get(
            f"/api/v1/documents/{DOCUMENT_ID}",
            headers={CORRELATION_HEADER: str(CORRELATION_ID)},
        )

    assert invalid.status_code == 400
    assert_openapi_response(invalid, path="/api/v1/documents", method="post")
    assert invalid.json()["code"] == "INVALID_DOCUMENT"
    assert invalid.json()["status"] == 400
    assert missing.status_code == 404
    assert_openapi_response(
        missing,
        path="/api/v1/documents/{documentId}",
        method="get",
    )
    assert missing.json()["code"] == "DOCUMENT_NOT_FOUND"
    assert missing.json()["status"] == 404


def test_health_and_readiness_distinguish_process_from_dependencies() -> None:
    storage = FakeStorage(ready=False)
    client, _repository, _storage = make_client(storage=storage)

    with client:
        health = client.get("/health")
        readiness = client.get("/ready")

    assert health.status_code == 200
    assert_openapi_response(health, path="/health", method="get")
    assert health.json() == {"status": "ok"}
    assert readiness.status_code == 503
    assert_openapi_response(readiness, path="/ready", method="get")
    assert readiness.json()["code"] == "DEPENDENCY_UNAVAILABLE"
    assert UUID(readiness.json()["correlationId"])


def test_readiness_is_ok_when_dependencies_are_reachable() -> None:
    client, _repository, _storage = make_client()
    with client:
        response = client.get("/ready")
    assert response.status_code == 200
    assert_openapi_response(response, path="/ready", method="get")
    assert response.json() == {"status": "ok"}


def test_completed_and_failed_statuses_emit_only_their_allowed_fields() -> None:
    repository = FakeRepository()
    repository.records[DOCUMENT_ID] = DocumentStatusRecord(
        document_id=DOCUMENT_ID,
        job_id=JOB_ID,
        status=ProcessingStatus.COMPLETED,
        created_at=NOW,
        started_at=NOW,
        completed_at=NOW,
        predicted_class="invoice",
        confidence=0.98,
        model_version="document-type-v1",
    )
    client, _repository, _storage = make_client(repository=repository)
    with client:
        completed = client.get(f"/api/v1/documents/{DOCUMENT_ID}")
    assert completed.status_code == 200
    assert_openapi_response(
        completed,
        path="/api/v1/documents/{documentId}",
        method="get",
    )
    assert completed.json()["classification"] == "invoice"
    assert "failureCode" not in completed.json()

    repository.records[DOCUMENT_ID] = DocumentStatusRecord(
        document_id=DOCUMENT_ID,
        job_id=JOB_ID,
        status=ProcessingStatus.FAILED,
        created_at=NOW,
        completed_at=NOW,
        failure_code="PDF_TEXT_EXTRACTION_FAILED",
    )
    with client:
        failed = client.get(f"/api/v1/documents/{DOCUMENT_ID}")
    assert failed.status_code == 200
    assert_openapi_response(
        failed,
        path="/api/v1/documents/{documentId}",
        method="get",
    )
    assert failed.json()["failureCode"] == "PDF_TEXT_EXTRACTION_FAILED"
    assert "classification" not in failed.json()


def test_unsupported_media_type_and_file_size_problem_match_contract() -> None:
    client, repository, storage = make_client()

    with client:
        unsupported = client.post(
            "/api/v1/documents",
            files={"file": ("image.png", b"not a PDF", "image/png")},
            headers={CORRELATION_HEADER: str(CORRELATION_ID)},
        )
        oversized = client.post(
            "/api/v1/documents",
            files={
                "file": (
                    "oversized.pdf",
                    b"%PDF-" + b"x" * (MAX_DOCUMENT_BYTES - 4),
                    "application/pdf",
                )
            },
            headers={CORRELATION_HEADER: str(CORRELATION_ID)},
        )

    assert unsupported.status_code == 415
    assert_openapi_response(unsupported, path="/api/v1/documents", method="post")
    assert oversized.status_code == 413
    assert_openapi_response(oversized, path="/api/v1/documents", method="post")
    assert not repository.submissions
    assert not storage.objects


def test_chunked_oversize_request_is_rejected_before_multipart_parsing() -> None:
    client, repository, storage = make_client()
    boundary = "reactorfront-boundary"
    prefix = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="large.pdf"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode()
    chunks = [prefix, b"%PDF-"]
    chunks.extend(
        b"x" * (64 * 1024)
        for _ in range((MAX_DOCUMENT_BYTES + MULTIPART_ENVELOPE_BYTES) // (64 * 1024) + 2)
    )
    chunks.append(f"\r\n--{boundary}--\r\n".encode())

    def chunked_body() -> object:
        yield from chunks

    with client:
        response = client.post(
            "/api/v1/documents",
            content=chunked_body(),
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                CORRELATION_HEADER: str(CORRELATION_ID),
            },
        )

    assert response.status_code == 413
    assert_openapi_response(response, path="/api/v1/documents", method="post")
    assert not repository.submissions
    assert not storage.objects
