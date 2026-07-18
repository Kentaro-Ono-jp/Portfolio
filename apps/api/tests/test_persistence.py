from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import TracebackType
from uuid import UUID

import pytest

import reactorfront_api.persistence as persistence
from reactorfront_api.domain import (
    DocumentSubmission,
    ProcessingStatus,
    SubmissionCommitState,
    SubmissionPersistenceError,
)
from reactorfront_api.persistence import (
    DocumentRow,
    OutboxEventRow,
    ProcessingJobRow,
    SqlAlchemySubmissionRepository,
)

DOCUMENT_ID = UUID("22222222-2222-4222-8222-222222222222")
JOB_ID = UUID("33333333-3333-4333-8333-333333333333")
EVENT_ID = UUID("44444444-4444-4444-8444-444444444444")
CORRELATION_ID = UUID("11111111-1111-4111-8111-111111111111")
NOW = datetime(2026, 7, 18, 9, 0, tzinfo=UTC)


@dataclass
class FakeTransaction:
    commit_error: Exception | None = None
    committed: bool = False
    rolled_back: bool = False

    def commit(self) -> None:
        if self.commit_error is not None:
            raise self.commit_error
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


@dataclass
class FakeSession:
    transaction: FakeTransaction = field(default_factory=FakeTransaction)
    flush_error: Exception | None = None
    rows: dict[type[object], object | None] = field(default_factory=dict)
    added: list[object] = field(default_factory=list)

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        return None

    def begin(self) -> FakeTransaction:
        return self.transaction

    def add(self, value: object) -> None:
        self.added.append(value)

    def flush(self) -> None:
        if self.flush_error is not None:
            raise self.flush_error

    def get(self, model: type[object], _identity: UUID) -> object | None:
        return self.rows.get(model)


def submission() -> DocumentSubmission:
    object_key = f"documents/{DOCUMENT_ID}/source.pdf"
    payload: dict[str, object] = {
        "eventId": str(EVENT_ID),
        "eventType": "document.processing.requested.v1",
        "occurredAt": "2026-07-18T09:00:00Z",
        "correlationId": str(CORRELATION_ID),
        "documentId": str(DOCUMENT_ID),
        "jobId": str(JOB_ID),
        "objectKey": object_key,
        "sourceSha256": "a" * 64,
    }
    return DocumentSubmission(
        document_id=DOCUMENT_ID,
        job_id=JOB_ID,
        event_id=EVENT_ID,
        correlation_id=CORRELATION_ID,
        original_filename="invoice.pdf",
        object_key=object_key,
        sha256="a" * 64,
        content_type="application/pdf",
        size_bytes=10,
        occurred_at=NOW,
        event_payload=payload,
    )


def repository_with_session(
    monkeypatch: pytest.MonkeyPatch,
    session: FakeSession,
) -> SqlAlchemySubmissionRepository:
    monkeypatch.setattr(persistence, "Session", lambda _engine: session)
    return SqlAlchemySubmissionRepository(engine=object())  # type: ignore[arg-type]


def test_save_flushes_all_rows_before_committing(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession()
    repository = repository_with_session(monkeypatch, session)

    repository.save(submission())

    assert [type(row) for row in session.added] == [
        DocumentRow,
        ProcessingJobRow,
        OutboxEventRow,
    ]
    assert session.transaction.committed
    assert not session.transaction.rolled_back


def test_save_marks_flush_failure_as_not_committed(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(flush_error=RuntimeError("constraint failure"))
    repository = repository_with_session(monkeypatch, session)

    with pytest.raises(SubmissionPersistenceError) as captured:
        repository.save(submission())

    assert captured.value.commit_state is SubmissionCommitState.NOT_COMMITTED
    assert session.transaction.rolled_back
    assert not session.transaction.committed


def test_save_marks_commit_exception_as_unresolved(monkeypatch: pytest.MonkeyPatch) -> None:
    transaction = FakeTransaction(commit_error=ConnectionError("acknowledgement lost"))
    session = FakeSession(transaction=transaction)
    repository = repository_with_session(monkeypatch, session)

    with pytest.raises(SubmissionPersistenceError) as captured:
        repository.save(submission())

    assert captured.value.commit_state is SubmissionCommitState.UNKNOWN
    assert not transaction.rolled_back


def test_commit_state_requires_all_three_matching_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = submission()
    document = DocumentRow(
        id=DOCUMENT_ID,
        original_filename="invoice.pdf",
        object_key=candidate.object_key,
        sha256=candidate.sha256,
        content_type="application/pdf",
        size_bytes=candidate.size_bytes,
        created_at=NOW,
    )
    job = ProcessingJobRow(
        id=JOB_ID,
        document_id=DOCUMENT_ID,
        status=ProcessingStatus.ACCEPTED.value,
        attempt_count=0,
        created_at=NOW,
    )
    outbox = OutboxEventRow(
        event_id=EVENT_ID,
        event_type=candidate.event_payload["eventType"],
        aggregate_id=JOB_ID,
        payload=candidate.event_payload,
        created_at=NOW,
        attempt_count=0,
    )
    session = FakeSession()
    repository = repository_with_session(monkeypatch, session)

    assert repository.get_submission_commit_state(candidate) is SubmissionCommitState.NOT_COMMITTED

    session.rows = {DocumentRow: document}
    assert repository.get_submission_commit_state(candidate) is SubmissionCommitState.INCONSISTENT

    session.rows = {
        DocumentRow: document,
        ProcessingJobRow: job,
        OutboxEventRow: outbox,
    }
    assert repository.get_submission_commit_state(candidate) is SubmissionCommitState.COMMITTED

    outbox.payload = {"unexpected": True}
    assert repository.get_submission_commit_state(candidate) is SubmissionCommitState.INCONSISTENT
