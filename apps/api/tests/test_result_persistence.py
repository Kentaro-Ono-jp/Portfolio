from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import TracebackType
from uuid import UUID, uuid5

import pytest

import reactorfront_api.persistence as persistence
from reactorfront_api.domain import (
    ProcessingStatus,
    ResultApplyOutcome,
    ResultEvent,
    ResultEventFailureCode,
    ResultEventInvariantError,
    ResultEventType,
)
from reactorfront_api.persistence import (
    DocumentRow,
    OutboxEventRow,
    ProcessingJobRow,
    ResultEventReceiptRow,
    SqlAlchemyResultEventRepository,
)

CORRELATION_ID = UUID("11111111-1111-4111-8111-111111111111")
DOCUMENT_ID = UUID("22222222-2222-4222-8222-222222222222")
JOB_ID = UUID("33333333-3333-4333-8333-333333333333")
REQUEST_EVENT_ID = UUID("44444444-4444-4444-8444-444444444444")
NOW = datetime(2026, 7, 20, 0, 0, tzinfo=UTC)
OBJECT_KEY = f"documents/{DOCUMENT_ID}/source.pdf"
SOURCE_SHA256 = "a" * 64


@dataclass
class FakeResultSession:
    scalar_values: list[object | None]
    rows: dict[type[object], object | None] = field(default_factory=dict)
    flushes: int = 0

    def __enter__(self) -> FakeResultSession:
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        return None

    def begin(self) -> FakeResultSession:
        return self

    def scalar(self, _statement: object) -> object | None:
        return self.scalar_values.pop(0)

    def get(self, model: type[object], _identity: UUID) -> object | None:
        return self.rows.get(model)

    def flush(self) -> None:
        self.flushes += 1


def result_event(
    event_type: ResultEventType,
    *,
    logical_payload_sha256: str = "b" * 64,
    model_version: str = "document-type-v1",
) -> ResultEvent:
    return ResultEvent(
        event_id=uuid5(REQUEST_EVENT_ID, event_type.value),
        event_type=event_type,
        occurred_at=NOW,
        correlation_id=CORRELATION_ID,
        document_id=DOCUMENT_ID,
        job_id=JOB_ID,
        object_key=OBJECT_KEY,
        source_sha256=SOURCE_SHA256,
        model_version=model_version,
        logical_payload_sha256=logical_payload_sha256,
        classification="invoice" if event_type is ResultEventType.COMPLETED else None,
        confidence=0.9876 if event_type is ResultEventType.COMPLETED else None,
        failure_code="SOURCE_DIGEST_MISMATCH" if event_type is ResultEventType.FAILED else None,
    )


def document() -> DocumentRow:
    return DocumentRow(
        id=DOCUMENT_ID,
        original_filename="invoice.pdf",
        object_key=OBJECT_KEY,
        sha256=SOURCE_SHA256,
        content_type="application/pdf",
        size_bytes=10,
        created_at=NOW,
    )


def job(status: ProcessingStatus) -> ProcessingJobRow:
    return ProcessingJobRow(
        id=JOB_ID,
        document_id=DOCUMENT_ID,
        status=status.value,
        attempt_count=0 if status is not ProcessingStatus.PROCESSING else 1,
        model_version="document-type-v1" if status is ProcessingStatus.PROCESSING else None,
        created_at=NOW,
        started_at=NOW if status is ProcessingStatus.PROCESSING else None,
    )


def requested() -> OutboxEventRow:
    payload: dict[str, object] = {
        "eventId": str(REQUEST_EVENT_ID),
        "eventType": "document.processing.requested.v1",
        "occurredAt": NOW.isoformat(),
        "correlationId": str(CORRELATION_ID),
        "documentId": str(DOCUMENT_ID),
        "jobId": str(JOB_ID),
        "objectKey": OBJECT_KEY,
        "sourceSha256": SOURCE_SHA256,
    }
    return OutboxEventRow(
        event_id=REQUEST_EVENT_ID,
        event_type="document.processing.requested.v1",
        aggregate_id=JOB_ID,
        payload=payload,
        created_at=NOW,
        published_at=NOW,
        attempt_count=1,
    )


def receipt(event: ResultEvent) -> ResultEventReceiptRow:
    return ResultEventReceiptRow(
        event_id=event.event_id,
        event_type=event.event_type.value,
        document_id=event.document_id,
        job_id=event.job_id,
        logical_payload_sha256=event.logical_payload_sha256,
        occurred_at=event.occurred_at,
        received_at=NOW,
    )


def repository_with_session(
    monkeypatch: pytest.MonkeyPatch,
    session: FakeResultSession,
) -> SqlAlchemyResultEventRepository:
    monkeypatch.setattr(persistence, "Session", lambda _engine: session)
    return SqlAlchemyResultEventRepository(engine=object())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("event_type", "initial_status", "expected_status"),
    [
        (ResultEventType.STARTED, ProcessingStatus.QUEUED, ProcessingStatus.PROCESSING),
        (ResultEventType.COMPLETED, ProcessingStatus.PROCESSING, ProcessingStatus.COMPLETED),
        (ResultEventType.FAILED, ProcessingStatus.PROCESSING, ProcessingStatus.FAILED),
    ],
)
def test_apply_commits_receipt_and_expected_transition(
    monkeypatch: pytest.MonkeyPatch,
    event_type: ResultEventType,
    initial_status: ProcessingStatus,
    expected_status: ProcessingStatus,
) -> None:
    candidate = result_event(event_type)
    processing_job = job(initial_status)
    session = FakeResultSession(
        scalar_values=[processing_job, requested(), candidate.event_id],
        rows={ResultEventReceiptRow: None, DocumentRow: document()},
    )
    repository = repository_with_session(monkeypatch, session)

    assert repository.apply(candidate) is ResultApplyOutcome.APPLIED
    assert processing_job.status == expected_status.value
    assert session.flushes == 1
    if event_type is ResultEventType.STARTED:
        assert processing_job.attempt_count == 1
        assert processing_job.started_at == NOW
    elif event_type is ResultEventType.COMPLETED:
        assert processing_job.predicted_class == "invoice"
        assert float(processing_job.confidence or 0) == 0.9876
        assert processing_job.failure_code is None
    else:
        assert processing_job.failure_code == "SOURCE_DIGEST_MISMATCH"
        assert processing_job.predicted_class is None
        assert processing_job.confidence is None


def test_apply_treats_matching_receipt_as_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = result_event(ResultEventType.COMPLETED)
    session = FakeResultSession(
        scalar_values=[job(ProcessingStatus.COMPLETED)],
        rows={ResultEventReceiptRow: receipt(candidate)},
    )

    assert (
        repository_with_session(monkeypatch, session).apply(candidate)
        is ResultApplyOutcome.DUPLICATE
    )


def test_apply_rejects_event_id_reuse(monkeypatch: pytest.MonkeyPatch) -> None:
    candidate = result_event(ResultEventType.COMPLETED)
    reused = receipt(candidate)
    reused.logical_payload_sha256 = "c" * 64
    session = FakeResultSession(
        scalar_values=[job(ProcessingStatus.COMPLETED)],
        rows={ResultEventReceiptRow: reused},
    )

    with pytest.raises(ResultEventInvariantError) as captured:
        repository_with_session(monkeypatch, session).apply(candidate)

    assert captured.value.code is ResultEventFailureCode.EVENT_ID_REUSE


@pytest.mark.parametrize(
    ("event_type", "status"),
    [
        (ResultEventType.STARTED, ProcessingStatus.ACCEPTED),
        (ResultEventType.COMPLETED, ProcessingStatus.QUEUED),
        (ResultEventType.FAILED, ProcessingStatus.ACCEPTED),
    ],
)
def test_apply_defers_valid_out_of_order_event(
    monkeypatch: pytest.MonkeyPatch,
    event_type: ResultEventType,
    status: ProcessingStatus,
) -> None:
    candidate = result_event(event_type)
    session = FakeResultSession(
        scalar_values=[job(status), requested()],
        rows={ResultEventReceiptRow: None, DocumentRow: document()},
    )

    assert (
        repository_with_session(monkeypatch, session).apply(candidate)
        is ResultApplyOutcome.DEFERRED
    )
    assert session.flushes == 0


def test_apply_rejects_unknown_job(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeResultSession(scalar_values=[None])

    with pytest.raises(ResultEventInvariantError) as captured:
        repository_with_session(monkeypatch, session).apply(result_event(ResultEventType.STARTED))

    assert captured.value.code is ResultEventFailureCode.IDENTITY_MISMATCH


def test_apply_rejects_cross_identity_event(monkeypatch: pytest.MonkeyPatch) -> None:
    candidate = result_event(ResultEventType.STARTED)
    mismatched_document = document()
    mismatched_document.sha256 = "f" * 64
    session = FakeResultSession(
        scalar_values=[job(ProcessingStatus.QUEUED), requested()],
        rows={ResultEventReceiptRow: None, DocumentRow: mismatched_document},
    )

    with pytest.raises(ResultEventInvariantError) as captured:
        repository_with_session(monkeypatch, session).apply(candidate)

    assert captured.value.code is ResultEventFailureCode.IDENTITY_MISMATCH


@pytest.mark.parametrize("status", [ProcessingStatus.COMPLETED, ProcessingStatus.FAILED])
def test_apply_preserves_first_terminal_state(
    monkeypatch: pytest.MonkeyPatch,
    status: ProcessingStatus,
) -> None:
    candidate = result_event(ResultEventType.FAILED)
    terminal_job = job(ProcessingStatus.PROCESSING)
    terminal_job.status = status.value
    session = FakeResultSession(
        scalar_values=[terminal_job, requested()],
        rows={ResultEventReceiptRow: None, DocumentRow: document()},
    )

    with pytest.raises(ResultEventInvariantError) as captured:
        repository_with_session(monkeypatch, session).apply(candidate)

    assert captured.value.code is ResultEventFailureCode.TERMINAL_CONFLICT


def test_apply_rejects_terminal_model_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    candidate = result_event(
        ResultEventType.COMPLETED,
        model_version="unexpected-model",
    )
    session = FakeResultSession(
        scalar_values=[job(ProcessingStatus.PROCESSING), requested()],
        rows={ResultEventReceiptRow: None, DocumentRow: document()},
    )

    with pytest.raises(ResultEventInvariantError) as captured:
        repository_with_session(monkeypatch, session).apply(candidate)

    assert captured.value.code is ResultEventFailureCode.IDENTITY_MISMATCH


def test_apply_handles_concurrent_matching_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = result_event(ResultEventType.STARTED)
    session = FakeResultSession(
        scalar_values=[job(ProcessingStatus.QUEUED), requested(), None],
        rows={ResultEventReceiptRow: receipt(candidate), DocumentRow: document()},
    )

    assert (
        repository_with_session(monkeypatch, session).apply(candidate)
        is ResultApplyOutcome.DUPLICATE
    )
