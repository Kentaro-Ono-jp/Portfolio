from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import TracebackType
from uuid import UUID, uuid5

import pytest

import reactorfront_api.persistence as persistence
from reactorfront_api.domain import (
    AuditAction,
    DocumentSubmission,
    OutboxInvariantError,
    ProcessingStatus,
    PublishFailureCode,
    PublishFinalizeResult,
    ReviewCommand,
    ReviewOperationError,
    ReviewOperationFailureCode,
    ReviewRecord,
    ReviewStatus,
    SubmissionCommitObservation,
    SubmissionCommitOutcome,
    SubmissionPersistenceError,
    review_entity_tag,
)
from reactorfront_api.persistence import (
    LEGACY_SYSTEM_PRINCIPAL_ID,
    AuditEventRow,
    DocumentRow,
    IdempotencyRecordRow,
    OutboxEventRow,
    ProcessingJobRow,
    ReviewDecisionRow,
    SqlAlchemyOutboxRepository,
    SqlAlchemySubmissionRepository,
)

DOCUMENT_ID = UUID("22222222-2222-4222-8222-222222222222")
JOB_ID = UUID("33333333-3333-4333-8333-333333333333")
EVENT_ID = UUID("44444444-4444-4444-8444-444444444444")
CORRELATION_ID = UUID("11111111-1111-4111-8111-111111111111")
NOW = datetime(2026, 7, 18, 9, 0, tzinfo=UTC)
REVIEW_ID = UUID("55555555-5555-4555-8555-555555555555")
IDEMPOTENCY_KEY = UUID("66666666-6666-4666-8666-666666666666")


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
class FakeReviewSession:
    scalar_values: list[object | None] = field(default_factory=list)
    get_rows: dict[tuple[type[object], UUID], object | None] = field(default_factory=dict)
    query_row: tuple[object, ...] | None = None
    scalar_rows: list[object] = field(default_factory=list)
    added: list[object] = field(default_factory=list)
    flushes: int = 0

    def __enter__(self) -> FakeReviewSession:
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        return None

    def begin(self) -> FakeReviewSession:
        return self

    def execute(self, _statement: object) -> FakeReviewSession:
        return self

    def one_or_none(self) -> FakeReviewRow | None:
        return FakeReviewRow(self.query_row) if self.query_row is not None else None

    def scalar(self, _statement: object) -> object | None:
        return self.scalar_values.pop(0)

    def scalars(self, _statement: object) -> FakeReviewScalars:
        return FakeReviewScalars(self.scalar_rows)

    def get(self, model: type[object], identity: UUID) -> object | None:
        return self.get_rows.get((model, identity))

    def add(self, value: object) -> None:
        self.added.append(value)

    def flush(self) -> None:
        self.flushes += 1


@dataclass(frozen=True)
class FakeReviewRow:
    values: tuple[object, ...]

    def _tuple(self) -> tuple[object, ...]:
        return self.values


@dataclass(frozen=True)
class FakeReviewScalars:
    values: list[object]

    def all(self) -> list[object]:
        return self.values


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
        submitted_by_principal_id=LEGACY_SYSTEM_PRINCIPAL_ID,
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


def review_repository_with_session(
    monkeypatch: pytest.MonkeyPatch,
    session: FakeReviewSession,
) -> SqlAlchemySubmissionRepository:
    monkeypatch.setattr(persistence, "Session", lambda _engine: session)
    return SqlAlchemySubmissionRepository(engine=object())  # type: ignore[arg-type]


def outbox_row(
    *,
    published: bool = False,
    lease_owner: str | None = "dispatcher-a",
    leased_until: datetime | None = NOW + timedelta(seconds=30),
    attempt_count: int = 1,
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
        attempt_count=attempt_count,
    )


def processing_job(*, status: ProcessingStatus = ProcessingStatus.ACCEPTED) -> ProcessingJobRow:
    return ProcessingJobRow(
        id=JOB_ID,
        document_id=DOCUMENT_ID,
        status=status.value,
        attempt_count=0,
        created_at=NOW,
    )


def completed_job() -> ProcessingJobRow:
    return ProcessingJobRow(
        id=JOB_ID,
        document_id=DOCUMENT_ID,
        status=ProcessingStatus.COMPLETED.value,
        attempt_count=1,
        model_version="document-type-v1",
        predicted_class="invoice",
        confidence=Decimal("0.9876"),
        created_at=NOW,
        started_at=NOW,
        completed_at=NOW,
    )


def review_command(*, final_classification: str = "invoice", if_match: str) -> ReviewCommand:
    return ReviewCommand(
        document_id=DOCUMENT_ID,
        principal_id=LEGACY_SYSTEM_PRINCIPAL_ID,
        correlation_id=CORRELATION_ID,
        final_classification=final_classification,
        if_match=if_match,
        idempotency_key=IDEMPOTENCY_KEY,
        request_digest={"invoice": "a" * 64, "report": "b" * 64}[final_classification],
        decision_id=REVIEW_ID,
        decided_at=NOW,
    )


def test_save_flushes_submission_and_audit_rows_before_committing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    repository = repository_with_session(monkeypatch, session)

    repository.save(submission())

    assert [type(row) for row in session.added] == [
        DocumentRow,
        ProcessingJobRow,
        OutboxEventRow,
        AuditEventRow,
    ]
    document = session.added[0]
    assert isinstance(document, DocumentRow)
    assert document.submitted_by_principal_id == LEGACY_SYSTEM_PRINCIPAL_ID
    assert session.flush_snapshots == [
        [DocumentRow],
        [DocumentRow, ProcessingJobRow],
        [DocumentRow, ProcessingJobRow, OutboxEventRow],
        [DocumentRow, ProcessingJobRow, OutboxEventRow, AuditEventRow],
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
        submitted_by_principal_id=LEGACY_SYSTEM_PRINCIPAL_ID,
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
    audit = AuditEventRow(
        id=uuid5(EVENT_ID, AuditAction.DOCUMENT_SUBMITTED.value),
        action=AuditAction.DOCUMENT_SUBMITTED.value,
        actor_principal_id=LEGACY_SYSTEM_PRINCIPAL_ID,
        document_id=DOCUMENT_ID,
        job_id=JOB_ID,
        review_id=None,
        correlation_id=CORRELATION_ID,
        causation_id=EVENT_ID,
        occurred_at=NOW,
        details_version=1,
        details={},
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
        AuditEventRow: audit,
    }
    assert repository.observe_submission_commit(candidate) is SubmissionCommitObservation.COMMITTED

    outbox.payload = {"unexpected": True}
    assert (
        repository.observe_submission_commit(candidate) is SubmissionCommitObservation.INCONSISTENT
    )


def test_review_read_write_replay_and_audit_are_one_terminal_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = DocumentRow(
        id=DOCUMENT_ID,
        submitted_by_principal_id=LEGACY_SYSTEM_PRINCIPAL_ID,
        original_filename="invoice.pdf",
        object_key=f"documents/{DOCUMENT_ID}/source.pdf",
        sha256="a" * 64,
        content_type="application/pdf",
        size_bytes=10,
        created_at=NOW,
    )
    job = completed_job()
    read_session = FakeReviewSession(query_row=(document, job, None))
    repository = review_repository_with_session(monkeypatch, read_session)

    current = repository.get_review(DOCUMENT_ID, LEGACY_SYSTEM_PRINCIPAL_ID)

    assert current == ReviewRecord(
        document_id=DOCUMENT_ID,
        job_id=JOB_ID,
        status=ReviewStatus.UNREVIEWED,
        machine_classification="invoice",
        machine_confidence=Decimal("0.9876"),
        model_version="document-type-v1",
        review_version=0,
    )

    write_session = FakeReviewSession(scalar_values=[document, None, job, None])
    repository = review_repository_with_session(monkeypatch, write_session)
    command = review_command(if_match=review_entity_tag(current))
    committed = repository.submit_review(command)

    assert committed.status is ReviewStatus.APPROVED
    assert committed.review_id == REVIEW_ID
    assert committed.final_classification == "invoice"
    assert committed.reviewer_principal_id == LEGACY_SYSTEM_PRINCIPAL_ID
    assert [type(row) for row in write_session.added] == [
        ReviewDecisionRow,
        IdempotencyRecordRow,
        AuditEventRow,
    ]
    assert write_session.flushes == 3
    audit = write_session.added[-1]
    assert isinstance(audit, AuditEventRow)
    assert audit.action == AuditAction.REVIEW_APPROVED.value
    assert audit.review_id == REVIEW_ID
    assert audit.details == {}

    decision = write_session.added[0]
    receipt = write_session.added[1]
    assert isinstance(decision, ReviewDecisionRow)
    assert isinstance(receipt, IdempotencyRecordRow)
    replay_session = FakeReviewSession(
        scalar_values=[document, receipt],
        get_rows={
            (ReviewDecisionRow, REVIEW_ID): decision,
            (ProcessingJobRow, JOB_ID): job,
        },
    )
    repository = review_repository_with_session(monkeypatch, replay_session)

    assert repository.submit_review(command) == committed
    assert replay_session.added == []

    conflict = review_command(
        final_classification="report",
        if_match=review_entity_tag(current),
    )
    conflict_session = FakeReviewSession(scalar_values=[document, receipt])
    repository = review_repository_with_session(monkeypatch, conflict_session)
    with pytest.raises(ReviewOperationError) as captured:
        repository.submit_review(conflict)
    assert captured.value.code is ReviewOperationFailureCode.IDEMPOTENCY_CONFLICT


def test_review_rejects_hidden_unavailable_terminal_and_stale_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = DocumentRow(
        id=DOCUMENT_ID,
        submitted_by_principal_id=LEGACY_SYSTEM_PRINCIPAL_ID,
        original_filename="invoice.pdf",
        object_key=f"documents/{DOCUMENT_ID}/source.pdf",
        sha256="a" * 64,
        content_type="application/pdf",
        size_bytes=10,
        created_at=NOW,
    )
    current = ReviewRecord(
        document_id=DOCUMENT_ID,
        job_id=JOB_ID,
        status=ReviewStatus.UNREVIEWED,
        machine_classification="invoice",
        machine_confidence=Decimal("0.9876"),
        model_version="document-type-v1",
        review_version=0,
    )

    unreachable_receipt = object()
    hidden_session = FakeReviewSession(scalar_values=[None, unreachable_receipt])
    hidden = review_repository_with_session(monkeypatch, hidden_session)
    with pytest.raises(ReviewOperationError) as captured:
        hidden.submit_review(review_command(if_match=review_entity_tag(current)))
    assert captured.value.code is ReviewOperationFailureCode.DOCUMENT_NOT_FOUND
    assert hidden_session.scalar_values == [unreachable_receipt]

    unavailable = review_repository_with_session(
        monkeypatch,
        FakeReviewSession(query_row=(document, processing_job(), None)),
    )
    with pytest.raises(ReviewOperationError) as captured:
        unavailable.get_review(DOCUMENT_ID, LEGACY_SYSTEM_PRINCIPAL_ID)
    assert captured.value.code is ReviewOperationFailureCode.REVIEW_NOT_AVAILABLE

    terminal = ReviewDecisionRow(
        id=REVIEW_ID,
        document_id=DOCUMENT_ID,
        job_id=JOB_ID,
        reviewer_principal_id=LEGACY_SYSTEM_PRINCIPAL_ID,
        machine_classification="invoice",
        final_classification="invoice",
        status=ReviewStatus.APPROVED.value,
        review_version=1,
        decided_at=NOW,
    )
    terminal_session = FakeReviewSession(scalar_values=[document, None, completed_job(), terminal])
    terminal_repository = review_repository_with_session(monkeypatch, terminal_session)
    terminal_record = ReviewRecord(
        document_id=DOCUMENT_ID,
        job_id=JOB_ID,
        status=ReviewStatus.APPROVED,
        machine_classification="invoice",
        machine_confidence=Decimal("0.9876"),
        model_version="document-type-v1",
        review_version=1,
        review_id=REVIEW_ID,
        final_classification="invoice",
        reviewer_principal_id=LEGACY_SYSTEM_PRINCIPAL_ID,
        decided_at=NOW,
    )
    with pytest.raises(ReviewOperationError) as captured:
        terminal_repository.submit_review(
            review_command(if_match=review_entity_tag(terminal_record))
        )
    assert captured.value.code is ReviewOperationFailureCode.REVIEW_NOT_AVAILABLE

    stale_session = FakeReviewSession(scalar_values=[document, None, completed_job(), None])
    stale_repository = review_repository_with_session(monkeypatch, stale_session)
    with pytest.raises(ReviewOperationError) as captured:
        stale_repository.submit_review(review_command(if_match='"stale"'))
    assert captured.value.code is ReviewOperationFailureCode.PRECONDITION_FAILED
    assert stale_session.added == []


def test_audit_history_requires_owner_and_preserves_database_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = AuditEventRow(
        id=uuid5(EVENT_ID, AuditAction.DOCUMENT_SUBMITTED.value),
        action=AuditAction.DOCUMENT_SUBMITTED.value,
        actor_principal_id=LEGACY_SYSTEM_PRINCIPAL_ID,
        document_id=DOCUMENT_ID,
        job_id=JOB_ID,
        review_id=None,
        correlation_id=CORRELATION_ID,
        causation_id=EVENT_ID,
        occurred_at=NOW,
        details_version=1,
        details={},
    )
    second = AuditEventRow(
        id=uuid5(REVIEW_ID, AuditAction.REVIEW_CORRECTED.value),
        action=AuditAction.REVIEW_CORRECTED.value,
        actor_principal_id=LEGACY_SYSTEM_PRINCIPAL_ID,
        document_id=DOCUMENT_ID,
        job_id=JOB_ID,
        review_id=REVIEW_ID,
        correlation_id=CORRELATION_ID,
        causation_id=REVIEW_ID,
        occurred_at=NOW + timedelta(seconds=1),
        details_version=1,
        details={},
    )
    session = FakeReviewSession(
        scalar_values=[DOCUMENT_ID],
        scalar_rows=[first, second],
    )
    repository = review_repository_with_session(monkeypatch, session)

    history = repository.get_audit_history(DOCUMENT_ID, LEGACY_SYSTEM_PRINCIPAL_ID)

    assert history is not None
    assert [event.action for event in history.events] == [
        AuditAction.DOCUMENT_SUBMITTED,
        AuditAction.REVIEW_CORRECTED,
    ]
    assert history.events[1].review_id == REVIEW_ID

    hidden = review_repository_with_session(
        monkeypatch,
        FakeReviewSession(scalar_values=[None]),
    )
    assert hidden.get_audit_history(DOCUMENT_ID, LEGACY_SYSTEM_PRINCIPAL_ID) is None


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

    result = repository.mark_published(
        event_id=EVENT_ID,
        lease_owner="dispatcher-a",
        attempt_count=1,
    )

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
        repository.mark_published(
            event_id=EVENT_ID,
            lease_owner="dispatcher-a",
            attempt_count=1,
        )
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
        repository.mark_published(
            event_id=EVENT_ID,
            lease_owner="dispatcher-a",
            attempt_count=1,
        )


@pytest.mark.parametrize(
    "event",
    [
        outbox_row(lease_owner="dispatcher-b"),
        outbox_row(attempt_count=2),
        outbox_row(leased_until=NOW),
    ],
)
def test_outbox_mark_published_refuses_stale_owner_or_attempt(
    monkeypatch: pytest.MonkeyPatch,
    event: OutboxEventRow,
) -> None:
    repository = outbox_repository_with_session(
        monkeypatch,
        FakeOutboxSession(scalar_values=[event, processing_job(), NOW]),
    )

    assert (
        repository.mark_published(
            event_id=EVENT_ID,
            lease_owner="dispatcher-a",
            attempt_count=1,
        )
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
        attempt_count=1,
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
        [outbox_row(attempt_count=2), NOW],
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
        attempt_count=1,
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
