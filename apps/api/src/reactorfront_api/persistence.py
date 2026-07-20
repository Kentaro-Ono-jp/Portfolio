from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from reactorfront_api.domain import (
    DocumentStatusRecord,
    DocumentSubmission,
    OutboxInvariantError,
    OutboxLease,
    ProcessingStatus,
    PublishFailureCode,
    PublishFinalizeResult,
    ResultApplyOutcome,
    ResultEvent,
    ResultEventFailureCode,
    ResultEventInvariantError,
    ResultEventType,
    SubmissionCommitObservation,
    SubmissionCommitOutcome,
    SubmissionPersistenceError,
)


class Base(DeclarativeBase):
    pass


class DocumentRow(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("size_bytes > 0 AND size_bytes <= 5242880", name="ck_documents_size"),
        CheckConstraint("sha256 ~ '^[a-f0-9]{64}$'", name="ck_documents_sha256"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    object_key: Mapped[str] = mapped_column(String(1024), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    content_type: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProcessingJobRow(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        UniqueConstraint("document_id", name="uq_processing_jobs_document_id"),
        CheckConstraint(
            "status IN ('accepted', 'queued', 'processing', 'completed', 'failed')",
            name="ck_processing_jobs_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_processing_jobs_attempt_count"),
        CheckConstraint(
            "predicted_class IS NULL OR predicted_class IN ('invoice', 'report')",
            name="ck_processing_jobs_class",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_processing_jobs_confidence",
        ),
        CheckConstraint(
            "failure_code IS NULL OR failure_code ~ '^[A-Z][A-Z0-9_]*$'",
            name="ck_processing_jobs_failure_code",
        ),
        CheckConstraint(
            "(status IN ('accepted', 'queued') AND started_at IS NULL "
            "AND completed_at IS NULL AND model_version IS NULL "
            "AND predicted_class IS NULL AND confidence IS NULL AND failure_code IS NULL) OR "
            "(status = 'processing' AND started_at IS NOT NULL AND completed_at IS NULL "
            "AND model_version IS NOT NULL AND predicted_class IS NULL "
            "AND confidence IS NULL AND failure_code IS NULL) OR "
            "(status = 'completed' AND started_at IS NOT NULL AND completed_at IS NOT NULL "
            "AND model_version IS NOT NULL AND predicted_class IS NOT NULL "
            "AND confidence IS NOT NULL AND failure_code IS NULL) OR "
            "(status = 'failed' AND completed_at IS NOT NULL AND predicted_class IS NULL "
            "AND confidence IS NULL AND failure_code IS NOT NULL)",
            name="ck_processing_jobs_state_shape",
        ),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    model_version: Mapped[str | None] = mapped_column(String(128))
    predicted_class: Mapped[str | None] = mapped_column(String(32))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    failure_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OutboxEventRow(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        CheckConstraint("attempt_count >= 0", name="ck_outbox_events_attempt_count"),
        CheckConstraint(
            "(leased_until IS NULL AND lease_owner IS NULL) OR "
            "(leased_until IS NOT NULL AND lease_owner IS NOT NULL)",
            name="ck_outbox_events_lease_pair",
        ),
        Index("ix_outbox_events_unpublished", "published_at", "created_at"),
    )

    event_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(255))
    aggregate_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("processing_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    leased_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)


class ResultEventReceiptRow(Base):
    __tablename__ = "result_event_receipts"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('document.processing.started.v1', "
            "'document.processing.completed.v1', 'document.processing.failed.v1')",
            name="ck_result_event_receipts_type",
        ),
        CheckConstraint(
            "logical_payload_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_result_event_receipts_payload_sha256",
        ),
        Index("ix_result_event_receipts_job", "job_id", "occurred_at"),
    )

    event_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(255))
    document_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    job_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("processing_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    logical_payload_sha256: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def create_database_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True)


class SqlAlchemySubmissionRepository:
    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine

    def save(self, submission: DocumentSubmission) -> None:
        with Session(self._engine) as session:
            transaction = session.begin()
            try:
                document = DocumentRow(
                    id=submission.document_id,
                    original_filename=submission.original_filename,
                    object_key=submission.object_key,
                    sha256=submission.sha256,
                    content_type=submission.content_type,
                    size_bytes=submission.size_bytes,
                    created_at=submission.occurred_at,
                )
                session.add(document)
                session.flush()

                job = ProcessingJobRow(
                    id=submission.job_id,
                    document_id=submission.document_id,
                    status=ProcessingStatus.ACCEPTED.value,
                    attempt_count=0,
                    created_at=submission.occurred_at,
                )
                session.add(job)
                session.flush()

                outbox_event = OutboxEventRow(
                    event_id=submission.event_id,
                    event_type=submission.event_payload["eventType"],
                    aggregate_id=submission.job_id,
                    payload=submission.event_payload,
                    created_at=submission.occurred_at,
                    attempt_count=0,
                )
                session.add(outbox_event)
                session.flush()
            except Exception as error:
                transaction.rollback()
                raise SubmissionPersistenceError(
                    commit_outcome=SubmissionCommitOutcome.NOT_COMMITTED
                ) from error

            try:
                transaction.commit()
            except Exception as error:
                raise SubmissionPersistenceError(
                    commit_outcome=SubmissionCommitOutcome.UNKNOWN
                ) from error

    def observe_submission_commit(
        self, submission: DocumentSubmission
    ) -> SubmissionCommitObservation:
        with Session(self._engine) as session:
            document = session.get(DocumentRow, submission.document_id)
            job = session.get(ProcessingJobRow, submission.job_id)
            outbox_event = session.get(OutboxEventRow, submission.event_id)

        if document is None and job is None and outbox_event is None:
            return SubmissionCommitObservation.ABSENT
        if document is None or job is None or outbox_event is None:
            return SubmissionCommitObservation.INCONSISTENT

        matches_submission = (
            document.object_key == submission.object_key
            and document.sha256 == submission.sha256
            and document.size_bytes == submission.size_bytes
            and job.document_id == submission.document_id
            and job.status == ProcessingStatus.ACCEPTED.value
            and outbox_event.aggregate_id == submission.job_id
            and outbox_event.event_type == submission.event_payload["eventType"]
            and outbox_event.payload == submission.event_payload
        )
        if matches_submission:
            return SubmissionCommitObservation.COMMITTED
        return SubmissionCommitObservation.INCONSISTENT

    def get_status(self, document_id: UUID) -> DocumentStatusRecord | None:
        statement = (
            select(DocumentRow, ProcessingJobRow)
            .join(ProcessingJobRow, ProcessingJobRow.document_id == DocumentRow.id)
            .where(DocumentRow.id == document_id)
        )
        with Session(self._engine) as session:
            result = session.execute(statement).one_or_none()
            if result is None:
                return None
            document, job = result._tuple()
            return DocumentStatusRecord(
                document_id=document.id,
                job_id=job.id,
                status=ProcessingStatus(job.status),
                created_at=job.created_at,
                started_at=job.started_at,
                completed_at=job.completed_at,
                predicted_class=job.predicted_class,
                confidence=float(job.confidence) if job.confidence is not None else None,
                model_version=job.model_version,
                failure_code=job.failure_code,
            )

    def is_ready(self) -> bool:
        with self._engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True

    def close(self) -> None:
        self._engine.dispose()


class SqlAlchemyOutboxRepository:
    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine

    def lease_pending(
        self,
        *,
        lease_owner: str,
        lease_duration: timedelta,
        batch_size: int,
    ) -> list[OutboxLease]:
        eligible = (
            select(OutboxEventRow.event_id)
            .where(OutboxEventRow.published_at.is_(None))
            .where(
                or_(
                    OutboxEventRow.leased_until.is_(None),
                    OutboxEventRow.leased_until <= func.now(),
                )
            )
            .order_by(OutboxEventRow.created_at, OutboxEventRow.event_id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
            .cte("eligible_outbox_events")
        )
        statement = (
            update(OutboxEventRow)
            .where(OutboxEventRow.event_id.in_(select(eligible.c.event_id)))
            .values(
                lease_owner=lease_owner,
                leased_until=func.now() + lease_duration,
                attempt_count=OutboxEventRow.attempt_count + 1,
            )
            .returning(OutboxEventRow)
        )
        with Session(self._engine) as session, session.begin():
            rows = list(session.scalars(statement))
            leases = [self._lease_from_row(row) for row in rows]
        return sorted(leases, key=lambda lease: (lease.created_at, lease.event_id))

    def mark_published(
        self,
        *,
        event_id: UUID,
        lease_owner: str,
        attempt_count: int,
    ) -> PublishFinalizeResult:
        with Session(self._engine) as session, session.begin():
            event = session.scalar(
                select(OutboxEventRow).where(OutboxEventRow.event_id == event_id).with_for_update()
            )
            if event is None:
                raise OutboxInvariantError("Outbox event does not exist")
            job = session.scalar(
                select(ProcessingJobRow)
                .where(ProcessingJobRow.id == event.aggregate_id)
                .with_for_update()
            )
            if job is None:
                raise OutboxInvariantError("Outbox job does not exist")

            if event.published_at is not None:
                if job.status != ProcessingStatus.QUEUED.value:
                    raise OutboxInvariantError("Published event does not have a queued job")
                return PublishFinalizeResult.ALREADY_PUBLISHED

            database_now = session.scalar(select(func.now()))
            if database_now is None:
                raise OutboxInvariantError("Database clock is unavailable")
            if (
                event.lease_owner != lease_owner
                or event.attempt_count != attempt_count
                or event.leased_until is None
                or event.leased_until <= database_now
            ):
                return PublishFinalizeResult.LEASE_LOST
            if job.status != ProcessingStatus.ACCEPTED.value:
                raise OutboxInvariantError("Unpublished event does not have an accepted job")

            event.published_at = database_now
            event.leased_until = None
            event.lease_owner = None
            event.last_error = None
            job.status = ProcessingStatus.QUEUED.value
            session.flush()
            return PublishFinalizeResult.PUBLISHED

    def record_failure(
        self,
        *,
        event_id: UUID,
        lease_owner: str,
        attempt_count: int,
        code: PublishFailureCode,
        retry_delay: timedelta,
    ) -> bool:
        with Session(self._engine) as session, session.begin():
            event = session.scalar(
                select(OutboxEventRow).where(OutboxEventRow.event_id == event_id).with_for_update()
            )
            if event is None or event.published_at is not None:
                return False
            database_now = session.scalar(select(func.now()))
            if database_now is None:
                return False
            if (
                event.lease_owner != lease_owner
                or event.attempt_count != attempt_count
                or event.leased_until is None
                or event.leased_until <= database_now
            ):
                return False
            event.leased_until = database_now + retry_delay
            event.last_error = code.value
            session.flush()
            return True

    def is_ready(self) -> bool:
        with self._engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True

    def close(self) -> None:
        self._engine.dispose()

    @staticmethod
    def _lease_from_row(row: OutboxEventRow) -> OutboxLease:
        if row.lease_owner is None or row.leased_until is None:
            raise OutboxInvariantError("Leased event has incomplete lease metadata")
        return OutboxLease(
            event_id=row.event_id,
            event_type=row.event_type,
            job_id=row.aggregate_id,
            payload=dict(row.payload),
            created_at=row.created_at,
            lease_owner=row.lease_owner,
            leased_until=row.leased_until,
            attempt_count=row.attempt_count,
        )


class SqlAlchemyResultEventRepository:
    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine

    def apply(self, event: ResultEvent) -> ResultApplyOutcome:
        with Session(self._engine) as session, session.begin():
            job = session.scalar(
                select(ProcessingJobRow)
                .where(ProcessingJobRow.id == event.job_id)
                .with_for_update()
            )
            if job is None:
                raise ResultEventInvariantError(code=ResultEventFailureCode.IDENTITY_MISMATCH)

            receipt = session.get(ResultEventReceiptRow, event.event_id)
            if receipt is not None:
                return self._duplicate_outcome(receipt=receipt, event=event)

            document = session.get(DocumentRow, event.document_id)
            requested = session.scalar(
                select(OutboxEventRow)
                .where(OutboxEventRow.aggregate_id == event.job_id)
                .where(OutboxEventRow.event_type == "document.processing.requested.v1")
            )
            self._require_identity(
                event=event,
                document=document,
                job=job,
                requested=requested,
            )

            if self._must_defer(event=event, job=job):
                return ResultApplyOutcome.DEFERRED
            self._require_transition(event=event, job=job)

            inserted_event_id = session.scalar(
                insert(ResultEventReceiptRow)
                .values(
                    event_id=event.event_id,
                    event_type=event.event_type.value,
                    document_id=event.document_id,
                    job_id=event.job_id,
                    logical_payload_sha256=event.logical_payload_sha256,
                    occurred_at=event.occurred_at,
                    received_at=func.now(),
                )
                .on_conflict_do_nothing(index_elements=[ResultEventReceiptRow.event_id])
                .returning(ResultEventReceiptRow.event_id)
            )
            if inserted_event_id is None:
                concurrent_receipt = session.get(ResultEventReceiptRow, event.event_id)
                if concurrent_receipt is None:
                    raise ResultEventInvariantError(code=ResultEventFailureCode.EVENT_ID_REUSE)
                return self._duplicate_outcome(receipt=concurrent_receipt, event=event)

            self._apply_transition(event=event, job=job)
            session.flush()
            return ResultApplyOutcome.APPLIED

    def is_ready(self) -> bool:
        with self._engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True

    def close(self) -> None:
        self._engine.dispose()

    @staticmethod
    def _duplicate_outcome(
        *,
        receipt: ResultEventReceiptRow,
        event: ResultEvent,
    ) -> ResultApplyOutcome:
        matches = (
            receipt.event_type == event.event_type.value
            and receipt.document_id == event.document_id
            and receipt.job_id == event.job_id
            and receipt.logical_payload_sha256 == event.logical_payload_sha256
        )
        if not matches:
            raise ResultEventInvariantError(code=ResultEventFailureCode.EVENT_ID_REUSE)
        return ResultApplyOutcome.DUPLICATE

    @staticmethod
    def _require_identity(
        *,
        event: ResultEvent,
        document: DocumentRow | None,
        job: ProcessingJobRow,
        requested: OutboxEventRow | None,
    ) -> None:
        if document is None or requested is None:
            raise ResultEventInvariantError(code=ResultEventFailureCode.IDENTITY_MISMATCH)
        requested_payload = requested.payload
        matches = (
            job.document_id == event.document_id
            and document.object_key == event.object_key
            and document.sha256 == event.source_sha256
            and requested_payload.get("eventId") == str(requested.event_id)
            and uuid5(requested.event_id, event.event_type.value) == event.event_id
            and requested_payload.get("correlationId") == str(event.correlation_id)
            and requested_payload.get("documentId") == str(event.document_id)
            and requested_payload.get("jobId") == str(event.job_id)
            and requested_payload.get("objectKey") == event.object_key
            and requested_payload.get("sourceSha256") == event.source_sha256
        )
        if not matches:
            raise ResultEventInvariantError(code=ResultEventFailureCode.IDENTITY_MISMATCH)

    @staticmethod
    def _must_defer(*, event: ResultEvent, job: ProcessingJobRow) -> bool:
        status = ProcessingStatus(job.status)
        if event.event_type is ResultEventType.STARTED:
            return status is ProcessingStatus.ACCEPTED
        return status in {ProcessingStatus.ACCEPTED, ProcessingStatus.QUEUED}

    @staticmethod
    def _require_transition(*, event: ResultEvent, job: ProcessingJobRow) -> None:
        status = ProcessingStatus(job.status)
        if event.event_type is ResultEventType.STARTED:
            if status is ProcessingStatus.QUEUED:
                return
        elif status is ProcessingStatus.PROCESSING:
            if job.model_version != event.model_version:
                raise ResultEventInvariantError(code=ResultEventFailureCode.IDENTITY_MISMATCH)
            if job.started_at is not None and event.occurred_at < job.started_at:
                raise ResultEventInvariantError(code=ResultEventFailureCode.INVALID_TRANSITION)
            return

        if status in {ProcessingStatus.COMPLETED, ProcessingStatus.FAILED}:
            raise ResultEventInvariantError(code=ResultEventFailureCode.TERMINAL_CONFLICT)
        raise ResultEventInvariantError(code=ResultEventFailureCode.INVALID_TRANSITION)

    @staticmethod
    def _apply_transition(*, event: ResultEvent, job: ProcessingJobRow) -> None:
        if event.event_type is ResultEventType.STARTED:
            job.status = ProcessingStatus.PROCESSING.value
            job.attempt_count += 1
            job.model_version = event.model_version
            job.started_at = event.occurred_at
            return

        job.completed_at = event.occurred_at
        if event.event_type is ResultEventType.COMPLETED:
            if event.classification is None or event.confidence is None:
                raise ResultEventInvariantError(code=ResultEventFailureCode.INVALID_EVENT)
            job.status = ProcessingStatus.COMPLETED.value
            job.predicted_class = event.classification
            job.confidence = Decimal(str(event.confidence))
            return

        if event.failure_code is None:
            raise ResultEventInvariantError(code=ResultEventFailureCode.INVALID_EVENT)
        job.status = ProcessingStatus.FAILED.value
        job.failure_code = event.failure_code
