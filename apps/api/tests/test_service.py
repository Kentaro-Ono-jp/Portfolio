from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID

import pytest

from reactorfront_api.domain import (
    DocumentStatusRecord,
    ProblemCode,
    ProcessingStatus,
    PublicProblem,
    SubmissionCommitObservation,
)
from reactorfront_api.service import MAX_DOCUMENT_BYTES, REQUESTED_EVENT_TYPE, DocumentService
from tests.fakes import FakeReadinessProbe, FakeRepository, FakeStorage, FakeValidator

IDS = (
    UUID("22222222-2222-4222-8222-222222222222"),
    UUID("33333333-3333-4333-8333-333333333333"),
    UUID("44444444-4444-4444-8444-444444444444"),
)
CORRELATION_ID = UUID("11111111-1111-4111-8111-111111111111")
NOW = datetime(2026, 7, 18, 9, 0, tzinfo=UTC)
PDF = b"%PDF-1.7\nportfolio test document"


def make_service(
    *,
    repository: FakeRepository | None = None,
    storage: FakeStorage | None = None,
    validator: FakeValidator | None = None,
    broker: FakeReadinessProbe | None = None,
) -> tuple[DocumentService, FakeRepository, FakeStorage, FakeValidator]:
    selected_repository = repository or FakeRepository()
    selected_storage = storage or FakeStorage()
    selected_validator = validator or FakeValidator()
    generated_ids = iter(IDS)
    return (
        DocumentService(
            repository=selected_repository,
            object_storage=selected_storage,
            event_validator=selected_validator,
            broker_readiness=broker,
            id_factory=lambda: next(generated_ids),
            clock=lambda: NOW,
        ),
        selected_repository,
        selected_storage,
        selected_validator,
    )


def assert_problem(call: object, *, status: int, code: ProblemCode) -> PublicProblem:
    with pytest.raises(PublicProblem) as captured:
        callable_object = call
        assert callable(callable_object)
        callable_object()
    assert captured.value.status == status
    assert captured.value.code is code
    assert captured.value.correlation_id == CORRELATION_ID
    return captured.value


def test_submit_persists_object_job_and_validated_outbox_event() -> None:
    service, repository, storage, validator = make_service()

    result = service.submit(
        stream=BytesIO(PDF),
        original_filename=r"C:\private\quarterly.pdf",
        content_type="application/pdf; charset=binary",
        correlation_id=CORRELATION_ID,
    )

    assert result.document_id == IDS[0]
    assert result.job_id == IDS[1]
    assert result.status is ProcessingStatus.ACCEPTED
    submission = repository.submissions[0]
    assert submission.original_filename == "quarterly.pdf"
    assert submission.object_key == f"documents/{IDS[0]}/source.pdf"
    assert submission.sha256 == hashlib.sha256(PDF).hexdigest()
    assert submission.size_bytes == len(PDF)
    assert storage.objects[submission.object_key] == (
        PDF,
        "application/pdf",
        submission.sha256,
    )
    assert validator.payloads == [(REQUESTED_EVENT_TYPE, submission.event_payload)]
    assert submission.event_payload == {
        "eventId": str(IDS[2]),
        "eventType": REQUESTED_EVENT_TYPE,
        "occurredAt": "2026-07-18T09:00:00Z",
        "correlationId": str(CORRELATION_ID),
        "documentId": str(IDS[0]),
        "jobId": str(IDS[1]),
        "objectKey": submission.object_key,
        "sourceSha256": submission.sha256,
    }


@pytest.mark.parametrize(
    ("content_type", "expected_status", "expected_code"),
    [
        (None, 415, ProblemCode.UNSUPPORTED_MEDIA_TYPE),
        ("image/png", 415, ProblemCode.UNSUPPORTED_MEDIA_TYPE),
    ],
)
def test_submit_rejects_unsupported_media_type(
    content_type: str | None,
    expected_status: int,
    expected_code: ProblemCode,
) -> None:
    service, repository, storage, _validator = make_service()

    assert_problem(
        lambda: service.submit(
            stream=BytesIO(PDF),
            original_filename="document.pdf",
            content_type=content_type,
            correlation_id=CORRELATION_ID,
        ),
        status=expected_status,
        code=expected_code,
    )
    assert not repository.submissions
    assert not storage.objects


def test_submit_rejects_invalid_pdf_signature() -> None:
    service, repository, storage, _validator = make_service()

    assert_problem(
        lambda: service.submit(
            stream=BytesIO(b"not a PDF"),
            original_filename="document.pdf",
            content_type="application/pdf",
            correlation_id=CORRELATION_ID,
        ),
        status=400,
        code=ProblemCode.INVALID_DOCUMENT,
    )
    assert not repository.submissions
    assert not storage.objects


def test_submit_accepts_exact_size_limit_and_rejects_one_extra_byte() -> None:
    accepted = b"%PDF-" + b"a" * (MAX_DOCUMENT_BYTES - 5)
    service, repository, _storage, _validator = make_service()
    service.submit(
        stream=BytesIO(accepted),
        original_filename=None,
        content_type="application/pdf",
        correlation_id=CORRELATION_ID,
    )
    assert repository.submissions[0].original_filename == "document.pdf"

    service, repository, storage, _validator = make_service()
    assert_problem(
        lambda: service.submit(
            stream=BytesIO(accepted + b"x"),
            original_filename="document.pdf",
            content_type="application/pdf",
            correlation_id=CORRELATION_ID,
        ),
        status=413,
        code=ProblemCode.DOCUMENT_TOO_LARGE,
    )
    assert not repository.submissions
    assert not storage.objects


def test_storage_failure_is_sanitized_without_database_write() -> None:
    storage = FakeStorage(put_error=RuntimeError("private storage detail"))
    service, repository, _storage, _validator = make_service(storage=storage)

    problem = assert_problem(
        lambda: service.submit(
            stream=BytesIO(PDF),
            original_filename="document.pdf",
            content_type="application/pdf",
            correlation_id=CORRELATION_ID,
        ),
        status=503,
        code=ProblemCode.DEPENDENCY_UNAVAILABLE,
    )
    assert "private storage detail" not in problem.detail
    assert not repository.submissions


@pytest.mark.parametrize("delete_fails", [False, True])
def test_database_failure_attempts_object_compensation(delete_fails: bool) -> None:
    repository = FakeRepository(save_error=RuntimeError("private database detail"))
    storage = FakeStorage(
        delete_error=RuntimeError("private delete detail") if delete_fails else None
    )
    service, _repository, _storage, _validator = make_service(
        repository=repository,
        storage=storage,
    )

    problem = assert_problem(
        lambda: service.submit(
            stream=BytesIO(PDF),
            original_filename="document.pdf",
            content_type="application/pdf",
            correlation_id=CORRELATION_ID,
        ),
        status=503,
        code=ProblemCode.DEPENDENCY_UNAVAILABLE,
    )
    assert "private database detail" not in problem.detail
    if delete_fails:
        assert storage.objects
    else:
        assert storage.deleted == [f"documents/{IDS[0]}/source.pdf"]
        assert not storage.objects


def test_lost_commit_acknowledgement_returns_accepted_without_deleting_source() -> None:
    repository = FakeRepository(
        commit_acknowledgement_error=ConnectionError("commit acknowledgement lost")
    )
    service, _repository, storage, _validator = make_service(repository=repository)

    result = service.submit(
        stream=BytesIO(PDF),
        original_filename="document.pdf",
        content_type="application/pdf",
        correlation_id=CORRELATION_ID,
    )

    assert result.status is ProcessingStatus.ACCEPTED
    assert storage.objects
    assert not storage.deleted


def test_lost_commit_acknowledgement_with_absent_observation_retains_source() -> None:
    repository = FakeRepository(
        commit_acknowledgement_error=ConnectionError("commit acknowledgement lost"),
        commit_observation_override=SubmissionCommitObservation.ABSENT,
    )
    service, _repository, storage, _validator = make_service(repository=repository)

    assert_problem(
        lambda: service.submit(
            stream=BytesIO(PDF),
            original_filename="document.pdf",
            content_type="application/pdf",
            correlation_id=CORRELATION_ID,
        ),
        status=503,
        code=ProblemCode.DEPENDENCY_UNAVAILABLE,
    )
    assert storage.objects
    assert not storage.deleted


def test_inconsistent_commit_observation_retains_source_for_reconciliation() -> None:
    repository = FakeRepository(
        commit_acknowledgement_error=ConnectionError("commit acknowledgement lost"),
        commit_observation_override=SubmissionCommitObservation.INCONSISTENT,
    )
    service, _repository, storage, _validator = make_service(repository=repository)

    assert_problem(
        lambda: service.submit(
            stream=BytesIO(PDF),
            original_filename="document.pdf",
            content_type="application/pdf",
            correlation_id=CORRELATION_ID,
        ),
        status=503,
        code=ProblemCode.DEPENDENCY_UNAVAILABLE,
    )
    assert storage.objects
    assert not storage.deleted


def test_failed_commit_observation_retains_source_for_reconciliation() -> None:
    repository = FakeRepository(
        commit_acknowledgement_error=ConnectionError("commit acknowledgement lost"),
        commit_observation_error=ConnectionError("database still unavailable"),
    )
    service, _repository, storage, _validator = make_service(repository=repository)

    assert_problem(
        lambda: service.submit(
            stream=BytesIO(PDF),
            original_filename="document.pdf",
            content_type="application/pdf",
            correlation_id=CORRELATION_ID,
        ),
        status=503,
        code=ProblemCode.DEPENDENCY_UNAVAILABLE,
    )
    assert storage.objects
    assert not storage.deleted


def test_unexpected_repository_failure_retains_source_conservatively() -> None:
    class UnexpectedFailureRepository(FakeRepository):
        def save(self, submission: object) -> None:
            raise RuntimeError("unexpected adapter failure")

    repository = UnexpectedFailureRepository()
    service, _repository, storage, _validator = make_service(repository=repository)

    assert_problem(
        lambda: service.submit(
            stream=BytesIO(PDF),
            original_filename="document.pdf",
            content_type="application/pdf",
            correlation_id=CORRELATION_ID,
        ),
        status=503,
        code=ProblemCode.DEPENDENCY_UNAVAILABLE,
    )
    assert storage.objects
    assert not storage.deleted


def test_get_status_returns_record_or_stable_problem() -> None:
    repository = FakeRepository()
    repository.records[IDS[0]] = DocumentStatusRecord(
        document_id=IDS[0],
        job_id=IDS[1],
        status=ProcessingStatus.ACCEPTED,
        created_at=NOW,
    )
    service, _repository, _storage, _validator = make_service(repository=repository)
    actual = service.get_status(document_id=IDS[0], correlation_id=CORRELATION_ID)
    assert actual == repository.records[IDS[0]]

    assert_problem(
        lambda: service.get_status(document_id=IDS[2], correlation_id=CORRELATION_ID),
        status=404,
        code=ProblemCode.DOCUMENT_NOT_FOUND,
    )

    repository.get_error = RuntimeError("private database detail")
    assert_problem(
        lambda: service.get_status(document_id=IDS[0], correlation_id=CORRELATION_ID),
        status=503,
        code=ProblemCode.DEPENDENCY_UNAVAILABLE,
    )


def test_readiness_and_close_cover_dependency_failures() -> None:
    broker = FakeReadinessProbe()
    service, repository, storage, _validator = make_service(broker=broker)
    assert service.is_ready()
    assert broker.calls == 1

    repository.ready = False
    assert not service.is_ready()

    repository.ready = True
    storage.readiness_error = RuntimeError("not reachable")
    assert not service.is_ready()
    assert broker.calls == 1

    storage.readiness_error = None
    broker.ready = False
    assert not service.is_ready()

    broker.ready = True
    broker.error = RuntimeError("broker unavailable")
    assert not service.is_ready()

    service.close()
    assert repository.closed
