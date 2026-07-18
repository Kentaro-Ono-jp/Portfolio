from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

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
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from reactorfront_api.domain import (
    DocumentStatusRecord,
    DocumentSubmission,
    ProcessingStatus,
    SubmissionCommitState,
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
                    commit_state=SubmissionCommitState.NOT_COMMITTED
                ) from error

            try:
                transaction.commit()
            except Exception as error:
                raise SubmissionPersistenceError(
                    commit_state=SubmissionCommitState.UNKNOWN
                ) from error

    def get_submission_commit_state(self, submission: DocumentSubmission) -> SubmissionCommitState:
        with Session(self._engine) as session:
            document = session.get(DocumentRow, submission.document_id)
            job = session.get(ProcessingJobRow, submission.job_id)
            outbox_event = session.get(OutboxEventRow, submission.event_id)

        if document is None and job is None and outbox_event is None:
            return SubmissionCommitState.NOT_COMMITTED
        if document is None or job is None or outbox_event is None:
            return SubmissionCommitState.INCONSISTENT

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
            return SubmissionCommitState.COMMITTED
        return SubmissionCommitState.INCONSISTENT

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
            document, job = result.tuple()
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
