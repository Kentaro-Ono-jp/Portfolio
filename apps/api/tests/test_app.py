from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import count
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from reactorfront_api.app import CORRELATION_HEADER, create_app, document_capability
from reactorfront_api.authentication import Capability
from reactorfront_api.domain import DocumentStatusRecord, ProcessingStatus
from reactorfront_api.request_limits import MULTIPART_ENVELOPE_BYTES
from reactorfront_api.service import MAX_DOCUMENT_BYTES, DocumentService
from tests.fakes import FakeRepository, FakeRequestAuthorizer, FakeStorage, FakeValidator
from tests.openapi_contract import assert_openapi_response

CORRELATION_ID = UUID("11111111-1111-4111-8111-111111111111")
DOCUMENT_ID = UUID("22222222-2222-4222-8222-222222222222")
JOB_ID = UUID("33333333-3333-4333-8333-333333333333")
EVENT_ID = UUID("44444444-4444-4444-8444-444444444444")
PRINCIPAL_ID = UUID("55555555-5555-4555-8555-555555555555")
REVIEW_ID = UUID("77777777-7777-4777-8777-777777777777")
IDEMPOTENCY_KEY = UUID("88888888-8888-4888-8888-888888888888")
NOW = datetime(2026, 7, 18, 9, 0, tzinfo=UTC)


def make_client(
    *,
    repository: FakeRepository | None = None,
    storage: FakeStorage | None = None,
) -> tuple[TestClient, FakeRepository, FakeStorage]:
    selected_repository = repository or FakeRepository()
    selected_storage = storage or FakeStorage()
    clock_ticks = count()
    ids = iter(
        (
            DOCUMENT_ID,
            JOB_ID,
            EVENT_ID,
            REVIEW_ID,
            UUID("99999999-9999-4999-8999-999999999999"),
            UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
        )
    )
    service = DocumentService(
        repository=selected_repository,
        object_storage=selected_storage,
        event_validator=FakeValidator(),
        id_factory=lambda: next(ids),
        clock=lambda: NOW + timedelta(seconds=next(clock_ticks)),
    )
    authorizer = FakeRequestAuthorizer(principal_id=PRINCIPAL_ID)
    return (
        TestClient(
            create_app(service=service, authorizer=authorizer),
            headers={"Authorization": "Bearer synthetic-access-token"},
        ),
        selected_repository,
        selected_storage,
    )


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("GET", f"/api/v1/documents/{DOCUMENT_ID}/review", Capability.DOCUMENTS_READ),
        ("PUT", f"/api/v1/documents/{DOCUMENT_ID}/review", Capability.REVIEWS_WRITE),
        ("GET", f"/api/v1/documents/{DOCUMENT_ID}/audit-events", Capability.AUDIT_READ),
    ],
)
def test_review_and_audit_routes_select_exact_capabilities(
    method: str,
    path: str,
    expected: Capability,
) -> None:
    assert document_capability(method, path) is expected


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


def test_private_source_is_verified_and_other_owner_matches_unknown_document() -> None:
    client, repository, _storage = make_client()
    with client:
        accepted = client.post(
            "/api/v1/documents",
            files={"file": ("invoice.pdf", b"%PDF-1.7\ntest", "application/pdf")},
            headers={CORRELATION_HEADER: str(CORRELATION_ID)},
        )
        source = client.get(
            f"/api/v1/documents/{DOCUMENT_ID}/source",
            headers={CORRELATION_HEADER: str(CORRELATION_ID)},
        )

    assert accepted.status_code == 202
    assert repository.submissions[0].submitted_by_principal_id == PRINCIPAL_ID
    assert source.status_code == 200
    assert source.content == b"%PDF-1.7\ntest"
    assert source.headers["Content-Type"] == "application/pdf"
    assert source.headers["Content-Disposition"] == 'inline; filename="source.pdf"'
    assert source.headers["X-Content-Type-Options"] == "nosniff"
    assert source.headers["Content-Length"] == str(len(source.content))
    assert source.headers["ETag"].startswith('"')
    assert source.headers[CORRELATION_HEADER] == str(CORRELATION_ID)

    repository.owners[DOCUMENT_ID] = UUID("66666666-6666-4666-8666-666666666666")
    with client:
        hidden_source = client.get(f"/api/v1/documents/{DOCUMENT_ID}/source")
        hidden_status = client.get(f"/api/v1/documents/{DOCUMENT_ID}")
        unknown_source = client.get("/api/v1/documents/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/source")

    assert hidden_source.status_code == 404
    assert hidden_status.status_code == 404
    assert unknown_source.status_code == 404
    assert hidden_source.json()["code"] == unknown_source.json()["code"]


def test_review_decision_etag_idempotency_and_audit_contract() -> None:
    client, repository, _storage = make_client()
    with client:
        accepted = client.post(
            "/api/v1/documents",
            files={"file": ("invoice.pdf", b"%PDF-1.7\ntest", "application/pdf")},
            headers={CORRELATION_HEADER: str(CORRELATION_ID)},
        )
        assert accepted.status_code == 202
        repository.records[DOCUMENT_ID] = DocumentStatusRecord(
            document_id=DOCUMENT_ID,
            job_id=JOB_ID,
            status=ProcessingStatus.COMPLETED,
            created_at=NOW,
            started_at=NOW,
            completed_at=NOW,
            predicted_class="invoice",
            confidence=0.9876,
            model_version="document-type-v1",
        )
        current = client.get(
            f"/api/v1/documents/{DOCUMENT_ID}/review",
            headers={CORRELATION_HEADER: str(CORRELATION_ID)},
        )

        missing_precondition = client.put(
            f"/api/v1/documents/{DOCUMENT_ID}/review",
            json={"finalClassification": "invoice"},
            headers={
                "Idempotency-Key": str(IDEMPOTENCY_KEY),
                CORRELATION_HEADER: str(CORRELATION_ID),
            },
        )
        stale = client.put(
            f"/api/v1/documents/{DOCUMENT_ID}/review",
            json={"finalClassification": "invoice"},
            headers={
                "If-Match": f'"{"0" * 64}"',
                "Idempotency-Key": str(IDEMPOTENCY_KEY),
                CORRELATION_HEADER: str(CORRELATION_ID),
            },
        )
        committed = client.put(
            f"/api/v1/documents/{DOCUMENT_ID}/review",
            json={"finalClassification": "invoice"},
            headers={
                "If-Match": current.headers["ETag"],
                "Idempotency-Key": str(IDEMPOTENCY_KEY),
                CORRELATION_HEADER: str(CORRELATION_ID),
            },
        )
        replay = client.put(
            f"/api/v1/documents/{DOCUMENT_ID}/review",
            json={"finalClassification": "invoice"},
            headers={
                "If-Match": current.headers["ETag"],
                "Idempotency-Key": str(IDEMPOTENCY_KEY),
                CORRELATION_HEADER: str(CORRELATION_ID),
            },
        )
        conflict = client.put(
            f"/api/v1/documents/{DOCUMENT_ID}/review",
            json={"finalClassification": "report"},
            headers={
                "If-Match": current.headers["ETag"],
                "Idempotency-Key": str(IDEMPOTENCY_KEY),
                CORRELATION_HEADER: str(CORRELATION_ID),
            },
        )
        audit = client.get(
            f"/api/v1/documents/{DOCUMENT_ID}/audit-events",
            headers={CORRELATION_HEADER: str(CORRELATION_ID)},
        )

    assert current.status_code == 200
    assert_openapi_response(
        current,
        path="/api/v1/documents/{documentId}/review",
        method="get",
    )
    assert current.json() == {
        "documentId": str(DOCUMENT_ID),
        "jobId": str(JOB_ID),
        "status": "unreviewed",
        "machineClassification": "invoice",
        "machineConfidence": 0.9876,
        "modelVersion": "document-type-v1",
        "reviewVersion": 0,
    }
    assert missing_precondition.status_code == 428
    assert_openapi_response(
        missing_precondition,
        path="/api/v1/documents/{documentId}/review",
        method="put",
    )
    assert missing_precondition.json()["code"] == "PRECONDITION_REQUIRED"
    assert stale.status_code == 412
    assert_openapi_response(
        stale,
        path="/api/v1/documents/{documentId}/review",
        method="put",
    )
    assert stale.json()["code"] == "PRECONDITION_FAILED"
    assert committed.status_code == 200
    assert_openapi_response(
        committed,
        path="/api/v1/documents/{documentId}/review",
        method="put",
    )
    assert committed.json()["status"] == "approved"
    assert committed.json()["finalClassification"] == "invoice"
    assert committed.json()["reviewerPrincipalId"] == str(PRINCIPAL_ID)
    assert committed.headers["ETag"] != current.headers["ETag"]
    assert replay.status_code == 200
    assert replay.json() == committed.json()
    assert replay.headers["ETag"] == committed.headers["ETag"]
    assert conflict.status_code == 409
    assert_openapi_response(
        conflict,
        path="/api/v1/documents/{documentId}/review",
        method="put",
    )
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert len(repository.reviews) == 1
    assert len(repository.idempotency_records) == 1
    assert audit.status_code == 200
    assert_openapi_response(
        audit,
        path="/api/v1/documents/{documentId}/audit-events",
        method="get",
    )
    assert [event["action"] for event in audit.json()["events"]] == [
        "document.submitted",
        "review.approved",
    ]


def test_request_validation_problems_match_contract_and_skip_service() -> None:
    client, repository, storage = make_client()

    with client:
        missing_file = client.post(
            "/api/v1/documents",
            data={"unexpected": "value"},
            headers={CORRELATION_HEADER: str(CORRELATION_ID)},
        )
        invalid_header = client.post(
            "/api/v1/documents",
            files={"file": ("invoice.pdf", b"%PDF-1.7\ntest", "application/pdf")},
            headers={CORRELATION_HEADER: "not-a-uuid"},
        )
        invalid_path = client.get(
            "/api/v1/documents/not-a-uuid",
            headers={CORRELATION_HEADER: str(CORRELATION_ID)},
        )

    contracts = [
        (missing_file, "/api/v1/documents", "post"),
        (invalid_header, "/api/v1/documents", "post"),
        (invalid_path, "/api/v1/documents/{documentId}", "get"),
    ]
    for response, path, method in contracts:
        assert response.status_code == 422
        assert_openapi_response(response, path=path, method=method)
        assert response.headers["content-type"].startswith("application/problem+json")
        problem = response.json()
        assert problem["type"] == "urn:reactorfront:problem:invalid-request"
        assert problem["title"] == "Invalid request"
        assert problem["status"] == 422
        assert problem["detail"] == "The request does not satisfy the API contract."
        assert problem["code"] == "INVALID_REQUEST"
        assert response.headers[CORRELATION_HEADER] == problem["correlationId"]

    assert missing_file.headers[CORRELATION_HEADER] == str(CORRELATION_ID)
    assert UUID(invalid_header.headers[CORRELATION_HEADER])
    assert invalid_header.headers[CORRELATION_HEADER] != "not-a-uuid"
    assert invalid_path.headers[CORRELATION_HEADER] == str(CORRELATION_ID)
    assert not repository.submissions
    assert not storage.objects


def test_anonymous_malformed_document_requests_authenticate_before_validation() -> None:
    client, repository, storage = make_client()
    client.headers.pop("Authorization")

    with client:
        missing_file = client.post(
            "/api/v1/documents",
            data={"unexpected": "value"},
            headers={CORRELATION_HEADER: str(CORRELATION_ID)},
        )
        invalid_path = client.get(
            "/api/v1/documents/not-a-uuid",
            headers={CORRELATION_HEADER: str(CORRELATION_ID)},
        )
        invalid_source_path = client.get(
            "/api/v1/documents/not-a-uuid/source",
            headers={CORRELATION_HEADER: str(CORRELATION_ID)},
        )
        invalid_review = client.put(
            "/api/v1/documents/not-a-uuid/review",
            json={"unexpected": True},
            headers={CORRELATION_HEADER: str(CORRELATION_ID)},
        )
        invalid_audit_path = client.get(
            "/api/v1/documents/not-a-uuid/audit-events",
            headers={CORRELATION_HEADER: str(CORRELATION_ID)},
        )

    contracts = [
        (missing_file, "/api/v1/documents", "post"),
        (invalid_path, "/api/v1/documents/{documentId}", "get"),
        (invalid_source_path, "/api/v1/documents/{documentId}/source", "get"),
        (invalid_review, "/api/v1/documents/{documentId}/review", "put"),
        (invalid_audit_path, "/api/v1/documents/{documentId}/audit-events", "get"),
    ]
    for response, path, method in contracts:
        assert response.status_code == 401
        assert_openapi_response(response, path=path, method=method)
        assert response.headers["content-type"].startswith("application/problem+json")
        assert response.headers[CORRELATION_HEADER] == str(CORRELATION_ID)
        assert response.json() == {
            "type": "urn:reactorfront:problem:authentication-required",
            "title": "Authentication required",
            "status": 401,
            "detail": "A valid bearer access token is required.",
            "code": "AUTHENTICATION_REQUIRED",
            "correlationId": str(CORRELATION_ID),
        }

    assert not repository.submissions
    assert not storage.objects


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
    repository.owners[DOCUMENT_ID] = PRINCIPAL_ID
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
    repository.owners[DOCUMENT_ID] = PRINCIPAL_ID
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
