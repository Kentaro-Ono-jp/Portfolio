from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import TracebackType
from uuid import UUID

import pytest

import reactorfront_api.persistence as persistence
from reactorfront_api.domain import (
    DocumentSubmission,
    OutboxInvariantError,
    ProcessingStatus,
    PublishFailureCode,
    PublishFinalizeResult,
    SubmissionCommitObservation,
    SubmissionCommitOutcome,
    SubmissionPersistenceError,
)
from reactorfront_api.persistence import (
    DocumentRow,
    OutboxEventRow,
    ProcessingJobRow,
    SqlAlchemyOutboxRepository,
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
    flush_error_at_call: int = 1
    rows: dict[type[object], object | None] = field(default_factory=dict)
    added: list[object] = field(default_factory=list)
    flush_snapshots: list[list[type[object]]] = field(default_factory=list)

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
        self.flush_snapshots.append([type(row) for row in self.added])
        if self.flush_error is not None and len(self.flush_snapshots) == self.flush_error_at_call:
            raise self.flush_error

    def get(self, model: type[object], _identity: UUID) -> object | None:
        return self.rows.get(model)


@dataclass
class FakeOutboxSession:
    returned_rows: list[OutboxEventRow] = field(default_factory=list)
    scalar_values: list[object | None] = field(default_factory=list)
    flushes: int = 0

    def __enter__(self) -> FakeOutboxSession:
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        return None

    def begin(self) -> FakeOutboxSession:
        return self

    def scalars(self, _statement: object) -> list[OutboxEventRow]:
        return self.returned_rows

    def scalar(self, _statement: object) -> object | None:
        return self.scalar_values.pop(0)

    def flush(self) -> None:
        self.flushes += 1


@dataclass
class FakeConnection:
    executed: list[object] = field(default_factory=list)

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        return None

    def execute(self, statement: object) -> None:
        self.executed.append(statement)


@dataclass
class FakeEngine:
    connection: FakeConnection = field(default_factory=FakeConnection)
    disposed: bool = False

    def connect(self) -> FakeConnection:
        return self.connection

    def dispose(self) -> None:
        self.disposed = True


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


def outbox_repository_with_session(
    monkeypatch: pytest.MonkeyPatch,
    session: FakeOutboxSession,
) -> SqlAlchemyOutboxRepository:
    monkeypatch.setattr(persistence, "Session", lambda _engine: session)
    return SqlAlchemyOutboxRepository(engine=object())  # type: ignore[arg-type]


def outbox_row(
    *,
    published: bool = False,
    lease_owner: str | None = "dispatcher-a",
    leased_until: datetime | None = NOW + timedelta(seconds=30),
) -> OutboxEventRow:
    candidate = submission()
    return OutboxEventRow(
        event_id=EVENT_ID,
        event_type=str(candidate.event_payload["eventType"]),
        aggregate_id=JOB_ID,
        payload=candidate.event_payload,
        created_at=NOW,
        published_at=NOW if published else None,
        lease_owner=lease_owner,
        leased_until=leased_until,
        attempt_count=1,
    )


def processing_job(*, status: ProcessingStatus = ProcessingStatus.ACCEPTED) -> ProcessingJobRow:
    return ProcessingJobRow(
        id=JOB_ID,
        document_id=DOCUMENT_ID,
        status=status.value,
        attempt_count=0,
        created_at=NOW,
    )


def test_save_flushes_all_rows_before_committing(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession()
    repository = repository_with_session(monkeypatch, session)

    repository.save(submission())

    assert [type(row) for row in session.added] == [
        DocumentRow,
        ProcessingJobRow,
        OutboxEventRow,
    ]
    assert session.flush_snapshots == [
        [DocumentRow],
        [DocumentRow, ProcessingJobRow],
        [DocumentRow, ProcessingJobRow, OutboxEventRow],
    ]
    assert session.transaction.committed
    assert not session.transaction.rolled_back


def test_save_marks_flush_failure_as_not_committed(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(
        flush_error=RuntimeError("constraint failure"),
        flush_error_at_call=3,
    )
    repository = repository_with_session(monkeypatch, session)

    with pytest.raises(SubmissionPersistenceError) as captured:
        repository.save(submission())

    assert captured.value.commit_outcome is SubmissionCommitOutcome.NOT_COMMITTED
    assert session.transaction.rolled_back
    assert not session.transaction.committed


def test_save_marks_commit_exception_as_unresolved(monkeypatch: pytest.MonkeyPatch) -> None:
    transaction = FakeTransaction(commit_error=ConnectionError("acknowledgement lost"))
    session = FakeSession(transaction=transaction)
    repository = repository_with_session(monkeypatch, session)

    with pytest.raises(SubmissionPersistenceError) as captured:
        repository.save(submission())

    assert captured.value.commit_outcome is SubmissionCommitOutcome.UNKNOWN
    assert not transaction.rolled_back


def test_commit_observation_requires_all_three_matching_rows(
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

    assert repository.observe_submission_commit(candidate) is SubmissionCommitObservation.ABSENT

    session.rows = {DocumentRow: document}
    assert (
        repository.observe_submission_commit(candidate) is SubmissionCommitObservation.INCONSISTENT
    )

    session.rows = {
        DocumentRow: document,
        ProcessingJobRow: job,
        OutboxEventRow: outbox,
    }
    assert repository.observe_submission_commit(candidate) is SubmissionCommitObservation.COMMITTED

    outbox.payload = {"unexpected": True}
    assert (
        repository.observe_submission_commit(candidate) is SubmissionCommitObservation.INCONSISTENT
    )


def test_outbox_lease_maps_owned_rows_and_rejects_incomplete_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    later = outbox_row()
    later.event_id = UUID("55555555-5555-4555-8555-555555555555")
    later.created_at = NOW + timedelta(seconds=1)
    earlier = outbox_row()
    session = FakeOutboxSession(returned_rows=[later, earlier])
    repository = outbox_repository_with_session(monkeypatch, session)

    leases = repository.lease_pending(
        lease_owner="dispatcher-a",
        lease_duration=timedelta(seconds=30),
        batch_size=8,
    )

    assert [item.event_id for item in leases] == [EVENT_ID, later.event_id]
    assert leases[0].payload == submission().event_payload
    assert leases[0].attempt_count == 1

    session.returned_rows = [outbox_row(lease_owner=None, leased_until=None)]
    with pytest.raises(OutboxInvariantError):
        repository.lease_pending(
            lease_owner="dispatcher-a",
            lease_duration=timedelta(seconds=30),
            batch_size=8,
        )


def test_outbox_mark_published_atomically_queues_the_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = outbox_row()
    job = processing_job()
    session = FakeOutboxSession(scalar_values=[event, job, NOW])
    repository = outbox_repository_with_session(monkeypatch, session)

    result = repository.mark_published(event_id=EVENT_ID, lease_owner="dispatcher-a")

    assert result is PublishFinalizeResult.PUBLISHED
    assert event.published_at == NOW
    assert event.lease_owner is None
    assert event.leased_until is None
    assert event.last_error is None
    assert job.status == ProcessingStatus.QUEUED.value
    assert session.flushes == 1


def test_outbox_mark_published_is_idempotent_for_matching_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = outbox_row(published=True, lease_owner=None, leased_until=None)
    job = processing_job(status=ProcessingStatus.QUEUED)
    repository = outbox_repository_with_session(
        monkeypatch,
        FakeOutboxSession(scalar_values=[event, job]),
    )

    assert (
        repository.mark_published(event_id=EVENT_ID, lease_owner="dispatcher-a")
        is PublishFinalizeResult.ALREADY_PUBLISHED
    )


@pytest.mark.parametrize(
    ("event", "job", "scalars"),
    [
        (None, None, [None]),
        (outbox_row(), None, [outbox_row(), None]),
        (
            outbox_row(published=True, lease_owner=None, leased_until=None),
            processing_job(),
            [
                outbox_row(published=True, lease_owner=None, leased_until=None),
                processing_job(),
            ],
        ),
        (
            outbox_row(),
            processing_job(status=ProcessingStatus.FAILED),
            [outbox_row(), processing_job(status=ProcessingStatus.FAILED), NOW],
        ),
    ],
)
def test_outbox_mark_published_rejects_inconsistent_state(
    monkeypatch: pytest.MonkeyPatch,
    event: OutboxEventRow | None,
    job: ProcessingJobRow | None,
    scalars: list[object | None],
) -> None:
    del event, job
    repository = outbox_repository_with_session(
        monkeypatch,
        FakeOutboxSession(scalar_values=scalars),
    )

    with pytest.raises(OutboxInvariantError):
        repository.mark_published(event_id=EVENT_ID, lease_owner="dispatcher-a")


@pytest.mark.parametrize(
    "event",
    [
        outbox_row(lease_owner="dispatcher-b"),
        outbox_row(leased_until=NOW),
    ],
)
def test_outbox_mark_published_refuses_stale_owner(
    monkeypatch: pytest.MonkeyPatch,
    event: OutboxEventRow,
) -> None:
    repository = outbox_repository_with_session(
        monkeypatch,
        FakeOutboxSession(scalar_values=[event, processing_job(), NOW]),
    )

    assert (
        repository.mark_published(event_id=EVENT_ID, lease_owner="dispatcher-a")
        is PublishFinalizeResult.LEASE_LOST
    )


def test_outbox_failure_records_only_owned_active_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = outbox_row()
    session = FakeOutboxSession(scalar_values=[event, NOW])
    repository = outbox_repository_with_session(monkeypatch, session)

    assert repository.record_failure(
        event_id=EVENT_ID,
        lease_owner="dispatcher-a",
        code=PublishFailureCode.UNROUTABLE,
        retry_delay=timedelta(seconds=4),
    )
    assert event.last_error == PublishFailureCode.UNROUTABLE.value
    assert event.leased_until == NOW + timedelta(seconds=4)
    assert session.flushes == 1


@pytest.mark.parametrize(
    "scalars",
    [
        [None],
        [outbox_row(published=True, lease_owner=None, leased_until=None)],
        [outbox_row(lease_owner="dispatcher-b"), NOW],
        [outbox_row(leased_until=NOW), NOW],
        [outbox_row(), None],
    ],
)
def test_outbox_failure_does_not_overwrite_unowned_or_completed_state(
    monkeypatch: pytest.MonkeyPatch,
    scalars: list[object | None],
) -> None:
    repository = outbox_repository_with_session(
        monkeypatch,
        FakeOutboxSession(scalar_values=scalars),
    )

    assert not repository.record_failure(
        event_id=EVENT_ID,
        lease_owner="dispatcher-a",
        code=PublishFailureCode.BROKER_UNAVAILABLE,
        retry_delay=timedelta(seconds=1),
    )


def test_outbox_repository_readiness_and_close() -> None:
    engine = FakeEngine()
    repository = SqlAlchemyOutboxRepository(engine=engine)  # type: ignore[arg-type]

    assert repository.is_ready()
    assert len(engine.connection.executed) == 1
    repository.close()
    assert engine.disposed
