from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4, uuid5

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
    AuditAction,
    AuditEventRecord,
    AuditHistory,
    DocumentSourceRecord,
    DocumentStatusRecord,
    DocumentSubmission,
    MeasuredModelEvidence,
    OutboxInvariantError,
    OutboxLease,
    PrincipalKind,
    PrincipalRecord,
    ProcessingStatus,
    PublishFailureCode,
    PublishFinalizeResult,
    ResultApplyOutcome,
    ResultEvent,
    ResultEventFailureCode,
    ResultEventInvariantError,
    ResultEventType,
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
from reactorfront_api.feedback_export import FeedbackObservation

LEGACY_SYSTEM_PRINCIPAL_ID = UUID("00000000-0000-4000-8000-000000000001")
LEGACY_SYSTEM_PRINCIPAL_KEY = "legacy-first-slice"
API_SYSTEM_PRINCIPAL_ID = UUID("00000000-0000-4000-8000-000000000002")
API_SYSTEM_PRINCIPAL_KEY = "api-processing"
REVIEW_OPERATION = "document.review.put"


class Base(DeclarativeBase):
    pass


class PrincipalRow(Base):
    __tablename__ = "principals"
    __table_args__ = (
        CheckConstraint(
            "(kind = 'oidc' AND issuer IS NOT NULL AND length(issuer) > 0 "
            "AND subject IS NOT NULL AND length(subject) > 0 AND system_key IS NULL) OR "
            "(kind = 'system' AND issuer IS NULL AND subject IS NULL "
            "AND system_key IS NOT NULL AND length(system_key) > 0)",
            name="ck_principals_identity_shape",
        ),
        CheckConstraint("kind IN ('oidc', 'system')", name="ck_principals_kind"),
        UniqueConstraint("issuer", "subject", name="uq_principals_oidc_identity"),
        UniqueConstraint("system_key", name="uq_principals_system_key"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    issuer: Mapped[str | None] = mapped_column(String(2048))
    subject: Mapped[str | None] = mapped_column(String(255))
    system_key: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DocumentRow(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("size_bytes > 0 AND size_bytes <= 5242880", name="ck_documents_size"),
        CheckConstraint("sha256 ~ '^[a-f0-9]{64}$'", name="ck_documents_sha256"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    submitted_by_principal_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("principals.id", ondelete="RESTRICT"),
        nullable=False,
    )
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
            "dataset_sha256 IS NULL OR dataset_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_processing_jobs_dataset_sha256",
        ),
        CheckConstraint(
            "artifact_sha256 IS NULL OR artifact_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_processing_jobs_artifact_sha256",
        ),
        CheckConstraint(
            "evaluation_policy_sha256 IS NULL OR evaluation_policy_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_processing_jobs_evaluation_policy_sha256",
        ),
        CheckConstraint(
            "evaluation_report_sha256 IS NULL OR evaluation_report_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_processing_jobs_evaluation_report_sha256",
        ),
        CheckConstraint(
            "(dataset_version IS NULL AND dataset_sha256 IS NULL "
            "AND preprocessing_version IS NULL AND pipeline_version IS NULL "
            "AND artifact_sha256 IS NULL AND evaluation_policy_version IS NULL "
            "AND evaluation_policy_sha256 IS NULL AND evaluation_report_sha256 IS NULL) OR "
            "(status = 'completed' AND dataset_version IS NOT NULL "
            "AND dataset_sha256 IS NOT NULL AND preprocessing_version IS NOT NULL "
            "AND pipeline_version IS NOT NULL AND artifact_sha256 IS NOT NULL "
            "AND evaluation_policy_version IS NOT NULL "
            "AND evaluation_policy_sha256 IS NOT NULL "
            "AND evaluation_report_sha256 IS NOT NULL)",
            name="ck_processing_jobs_model_evidence_shape",
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
    dataset_version: Mapped[str | None] = mapped_column(String(128))
    dataset_sha256: Mapped[str | None] = mapped_column(String(64))
    preprocessing_version: Mapped[str | None] = mapped_column(String(128))
    pipeline_version: Mapped[str | None] = mapped_column(String(128))
    artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    evaluation_policy_version: Mapped[str | None] = mapped_column(String(128))
    evaluation_policy_sha256: Mapped[str | None] = mapped_column(String(64))
    evaluation_report_sha256: Mapped[str | None] = mapped_column(String(64))
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
            "'document.processing.completed.v1', 'document.processing.completed.v2', "
            "'document.processing.failed.v1')",
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


class ReviewDecisionRow(Base):
    __tablename__ = "review_decisions"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_review_decisions_job_id"),
        CheckConstraint(
            "machine_classification IN ('invoice', 'report')",
            name="ck_review_decisions_machine_classification",
        ),
        CheckConstraint(
            "final_classification IN ('invoice', 'report')",
            name="ck_review_decisions_final_classification",
        ),
        CheckConstraint(
            "status IN ('approved', 'corrected')",
            name="ck_review_decisions_status",
        ),
        CheckConstraint("review_version = 1", name="ck_review_decisions_version"),
        CheckConstraint(
            "(status = 'approved' AND machine_classification = final_classification) OR "
            "(status = 'corrected' AND machine_classification <> final_classification)",
            name="ck_review_decisions_status_matches_classification",
        ),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    job_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("processing_jobs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reviewer_principal_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("principals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    machine_classification: Mapped[str] = mapped_column(String(32))
    final_classification: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    review_version: Mapped[int] = mapped_column(Integer)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IdempotencyRecordRow(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "principal_id",
            "operation",
            "idempotency_key",
            name="uq_idempotency_records_namespace",
        ),
        CheckConstraint(
            "request_digest ~ '^[a-f0-9]{64}$'",
            name="ck_idempotency_records_request_digest",
        ),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    principal_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("principals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    operation: Mapped[str] = mapped_column(String(128))
    idempotency_key: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True))
    target_document_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    request_digest: Mapped[str] = mapped_column(String(64))
    review_decision_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("review_decisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditEventRow(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "action IN ('document.submitted', 'processing.completed', "
            "'processing.failed', 'review.approved', 'review.corrected')",
            name="ck_audit_events_action",
        ),
        CheckConstraint(
            "details_version = 1 OR (details_version = 2 AND action = 'processing.completed')",
            name="ck_audit_events_details_version",
        ),
        UniqueConstraint("action", "causation_id", name="uq_audit_events_causation"),
        Index("ix_audit_events_document_order", "document_id", "occurred_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    action: Mapped[str] = mapped_column(String(64))
    actor_principal_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("principals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    document_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    job_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("processing_jobs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    review_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("review_decisions.id", ondelete="RESTRICT"),
    )
    correlation_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True))
    causation_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    details_version: Mapped[int] = mapped_column(Integer)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB)


def create_database_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True)


class SqlAlchemyPrincipalRepository:
    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine

    def resolve_oidc_principal(self, *, issuer: str, subject: str) -> PrincipalRecord:
        if not issuer or len(issuer) > 2048 or not subject or len(subject) > 255:
            raise ValueError("OIDC issuer and subject must be non-empty and bounded.")
        principal_id = uuid4()
        created_at = datetime.now(UTC)
        statement = (
            insert(PrincipalRow)
            .values(
                id=principal_id,
                kind=PrincipalKind.OIDC.value,
                issuer=issuer,
                subject=subject,
                system_key=None,
                created_at=created_at,
            )
            .on_conflict_do_nothing(index_elements=[PrincipalRow.issuer, PrincipalRow.subject])
            .returning(PrincipalRow)
        )
        lookup = select(PrincipalRow).where(
            PrincipalRow.issuer == issuer,
            PrincipalRow.subject == subject,
        )
        with Session(self._engine) as session, session.begin():
            row = session.scalar(statement)
            if row is None:
                row = session.scalar(lookup)
            if row is None:
                raise RuntimeError("The stable OIDC principal could not be resolved.")
            return self._record_from_row(row)

    def close(self) -> None:
        self._engine.dispose()

    @staticmethod
    def _record_from_row(row: PrincipalRow) -> PrincipalRecord:
        return PrincipalRecord(
            principal_id=row.id,
            kind=PrincipalKind(row.kind),
            issuer=row.issuer,
            subject=row.subject,
            system_key=row.system_key,
            created_at=row.created_at,
        )


class SqlAlchemySubmissionRepository:
    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine

    def save(self, submission: DocumentSubmission) -> None:
        with Session(self._engine) as session:
            transaction = session.begin()
            try:
                document = DocumentRow(
                    id=submission.document_id,
                    submitted_by_principal_id=submission.submitted_by_principal_id,
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

                audit_event = AuditEventRow(
                    id=uuid5(
                        submission.event_id,
                        AuditAction.DOCUMENT_SUBMITTED.value,
                    ),
                    action=AuditAction.DOCUMENT_SUBMITTED.value,
                    actor_principal_id=submission.submitted_by_principal_id,
                    document_id=submission.document_id,
                    job_id=submission.job_id,
                    review_id=None,
                    correlation_id=submission.correlation_id,
                    causation_id=submission.event_id,
                    occurred_at=submission.occurred_at,
                    details_version=1,
                    details={},
                )
                session.add(audit_event)
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
            audit_event = session.get(
                AuditEventRow,
                uuid5(submission.event_id, AuditAction.DOCUMENT_SUBMITTED.value),
            )

        if document is None and job is None and outbox_event is None and audit_event is None:
            return SubmissionCommitObservation.ABSENT
        if document is None or job is None or outbox_event is None or audit_event is None:
            return SubmissionCommitObservation.INCONSISTENT

        matches_submission = (
            document.submitted_by_principal_id == submission.submitted_by_principal_id
            and document.object_key == submission.object_key
            and document.sha256 == submission.sha256
            and document.size_bytes == submission.size_bytes
            and job.document_id == submission.document_id
            and job.status == ProcessingStatus.ACCEPTED.value
            and outbox_event.aggregate_id == submission.job_id
            and outbox_event.event_type == submission.event_payload["eventType"]
            and outbox_event.payload == submission.event_payload
            and audit_event.action == AuditAction.DOCUMENT_SUBMITTED.value
            and audit_event.actor_principal_id == submission.submitted_by_principal_id
            and audit_event.document_id == submission.document_id
            and audit_event.job_id == submission.job_id
            and audit_event.correlation_id == submission.correlation_id
            and audit_event.causation_id == submission.event_id
            and audit_event.details_version == 1
            and audit_event.details == {}
        )
        if matches_submission:
            return SubmissionCommitObservation.COMMITTED
        return SubmissionCommitObservation.INCONSISTENT

    def get_status(self, document_id: UUID, principal_id: UUID) -> DocumentStatusRecord | None:
        statement = (
            select(DocumentRow, ProcessingJobRow)
            .join(ProcessingJobRow, ProcessingJobRow.document_id == DocumentRow.id)
            .where(
                DocumentRow.id == document_id,
                DocumentRow.submitted_by_principal_id == principal_id,
            )
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
                model_evidence=self._model_evidence(job),
                failure_code=job.failure_code,
            )

    def get_source(self, document_id: UUID, principal_id: UUID) -> DocumentSourceRecord | None:
        statement = select(DocumentRow).where(
            DocumentRow.id == document_id,
            DocumentRow.submitted_by_principal_id == principal_id,
        )
        with Session(self._engine) as session:
            document = session.scalar(statement)
            if document is None:
                return None
            return DocumentSourceRecord(
                document_id=document.id,
                original_filename=document.original_filename,
                object_key=document.object_key,
                sha256=document.sha256,
                content_type=document.content_type,
                size_bytes=document.size_bytes,
            )

    def get_review(self, document_id: UUID, principal_id: UUID) -> ReviewRecord | None:
        statement = (
            select(DocumentRow, ProcessingJobRow, ReviewDecisionRow)
            .join(ProcessingJobRow, ProcessingJobRow.document_id == DocumentRow.id)
            .outerjoin(ReviewDecisionRow, ReviewDecisionRow.job_id == ProcessingJobRow.id)
            .where(
                DocumentRow.id == document_id,
                DocumentRow.submitted_by_principal_id == principal_id,
            )
        )
        with Session(self._engine) as session:
            result = session.execute(statement).one_or_none()
            if result is None:
                return None
            _document, job, decision = result._tuple()
            return self._review_record(job=job, decision=decision)

    def submit_review(self, command: ReviewCommand) -> ReviewRecord:
        with Session(self._engine) as session, session.begin():
            session.execute(
                select(
                    func.pg_advisory_xact_lock(
                        self._idempotency_lock_key(
                            command.principal_id,
                            command.idempotency_key,
                        )
                    )
                )
            )
            document = session.scalar(
                select(DocumentRow)
                .where(
                    DocumentRow.id == command.document_id,
                    DocumentRow.submitted_by_principal_id == command.principal_id,
                )
                .with_for_update()
            )
            if document is None:
                raise ReviewOperationError(code=ReviewOperationFailureCode.DOCUMENT_NOT_FOUND)
            existing_receipt = session.scalar(
                select(IdempotencyRecordRow).where(
                    IdempotencyRecordRow.principal_id == command.principal_id,
                    IdempotencyRecordRow.operation == REVIEW_OPERATION,
                    IdempotencyRecordRow.idempotency_key == command.idempotency_key,
                )
            )
            if existing_receipt is not None:
                if (
                    existing_receipt.target_document_id != command.document_id
                    or existing_receipt.request_digest != command.request_digest
                ):
                    raise ReviewOperationError(code=ReviewOperationFailureCode.IDEMPOTENCY_CONFLICT)
                decision = session.get(
                    ReviewDecisionRow,
                    existing_receipt.review_decision_id,
                )
                if decision is None:
                    raise RuntimeError("Committed idempotency receipt has no review decision")
                job = session.get(ProcessingJobRow, decision.job_id)
                if job is None:
                    raise RuntimeError("Committed review decision has no processing job")
                return self._review_record(job=job, decision=decision)
            job = session.scalar(
                select(ProcessingJobRow)
                .where(ProcessingJobRow.document_id == document.id)
                .with_for_update()
            )
            if job is None:
                raise RuntimeError("Owned document has no processing job")
            existing_decision = session.scalar(
                select(ReviewDecisionRow).where(ReviewDecisionRow.job_id == job.id)
            )
            current = self._review_record(job=job, decision=existing_decision)
            if command.if_match != review_entity_tag(current):
                raise ReviewOperationError(code=ReviewOperationFailureCode.PRECONDITION_FAILED)
            if existing_decision is not None:
                raise ReviewOperationError(code=ReviewOperationFailureCode.REVIEW_NOT_AVAILABLE)

            review_status = (
                ReviewStatus.APPROVED
                if command.final_classification == current.machine_classification
                else ReviewStatus.CORRECTED
            )
            decision = ReviewDecisionRow(
                id=command.decision_id,
                document_id=document.id,
                job_id=job.id,
                reviewer_principal_id=command.principal_id,
                machine_classification=current.machine_classification,
                final_classification=command.final_classification,
                status=review_status.value,
                review_version=1,
                decided_at=command.decided_at,
            )
            session.add(decision)
            session.flush()

            receipt = IdempotencyRecordRow(
                id=uuid5(
                    command.principal_id,
                    f"{REVIEW_OPERATION}:{command.idempotency_key}",
                ),
                principal_id=command.principal_id,
                operation=REVIEW_OPERATION,
                idempotency_key=command.idempotency_key,
                target_document_id=document.id,
                request_digest=command.request_digest,
                review_decision_id=decision.id,
                created_at=command.decided_at,
            )
            session.add(receipt)
            session.flush()

            audit_action = (
                AuditAction.REVIEW_APPROVED
                if review_status is ReviewStatus.APPROVED
                else AuditAction.REVIEW_CORRECTED
            )
            session.add(
                AuditEventRow(
                    id=uuid5(decision.id, audit_action.value),
                    action=audit_action.value,
                    actor_principal_id=command.principal_id,
                    document_id=document.id,
                    job_id=job.id,
                    review_id=decision.id,
                    correlation_id=command.correlation_id,
                    causation_id=decision.id,
                    occurred_at=command.decided_at,
                    details_version=1,
                    details={},
                )
            )
            session.flush()
            return self._review_record(job=job, decision=decision)

    def get_audit_history(
        self,
        document_id: UUID,
        principal_id: UUID,
    ) -> AuditHistory | None:
        owned_document = select(DocumentRow.id).where(
            DocumentRow.id == document_id,
            DocumentRow.submitted_by_principal_id == principal_id,
        )
        events = (
            select(AuditEventRow)
            .where(AuditEventRow.document_id == document_id)
            .order_by(AuditEventRow.occurred_at, AuditEventRow.id)
        )
        with Session(self._engine) as session:
            if session.scalar(owned_document) is None:
                return None
            rows = session.scalars(events).all()
            return AuditHistory(
                document_id=document_id,
                events=tuple(
                    AuditEventRecord(
                        event_id=row.id,
                        action=AuditAction(row.action),
                        occurred_at=row.occurred_at,
                        actor_principal_id=row.actor_principal_id,
                        document_id=row.document_id,
                        job_id=row.job_id,
                        review_id=row.review_id,
                        correlation_id=row.correlation_id,
                        details_version=row.details_version,
                        details=dict(row.details),
                    )
                    for row in rows
                ),
            )

    @staticmethod
    def _idempotency_lock_key(principal_id: UUID, idempotency_key: UUID) -> int:
        digest = hashlib.sha256(principal_id.bytes + idempotency_key.bytes).digest()
        return int.from_bytes(digest[:8], byteorder="big", signed=True)

    @staticmethod
    def _review_record(
        *,
        job: ProcessingJobRow,
        decision: ReviewDecisionRow | None,
    ) -> ReviewRecord:
        if (
            job.status != ProcessingStatus.COMPLETED.value
            or job.predicted_class not in {"invoice", "report"}
            or job.confidence is None
            or job.model_version is None
        ):
            raise ReviewOperationError(code=ReviewOperationFailureCode.REVIEW_NOT_AVAILABLE)
        if decision is None:
            return ReviewRecord(
                document_id=job.document_id,
                job_id=job.id,
                status=ReviewStatus.UNREVIEWED,
                machine_classification=job.predicted_class,
                machine_confidence=job.confidence,
                model_version=job.model_version,
                review_version=0,
                model_evidence=SqlAlchemySubmissionRepository._model_evidence(job),
            )
        if (
            decision.document_id != job.document_id
            or decision.machine_classification != job.predicted_class
        ):
            raise RuntimeError("Review decision does not match immutable machine state")
        return ReviewRecord(
            document_id=job.document_id,
            job_id=job.id,
            status=ReviewStatus(decision.status),
            machine_classification=job.predicted_class,
            machine_confidence=job.confidence,
            model_version=job.model_version,
            review_version=decision.review_version,
            model_evidence=SqlAlchemySubmissionRepository._model_evidence(job),
            review_id=decision.id,
            final_classification=decision.final_classification,
            reviewer_principal_id=decision.reviewer_principal_id,
            decided_at=decision.decided_at,
        )

    @staticmethod
    def _model_evidence(job: ProcessingJobRow) -> MeasuredModelEvidence | None:
        values = (
            job.dataset_version,
            job.dataset_sha256,
            job.preprocessing_version,
            job.pipeline_version,
            job.artifact_sha256,
            job.evaluation_policy_version,
            job.evaluation_policy_sha256,
            job.evaluation_report_sha256,
        )
        if all(value is None for value in values):
            return None
        if any(value is None for value in values):
            raise RuntimeError("Persisted model evidence is incomplete")
        return MeasuredModelEvidence(
            dataset_version=str(job.dataset_version),
            dataset_sha256=str(job.dataset_sha256),
            preprocessing_version=str(job.preprocessing_version),
            pipeline_version=str(job.pipeline_version),
            artifact_sha256=str(job.artifact_sha256),
            evaluation_policy_version=str(job.evaluation_policy_version),
            evaluation_policy_sha256=str(job.evaluation_policy_sha256),
            evaluation_report_sha256=str(job.evaluation_report_sha256),
        )

    def is_ready(self) -> bool:
        with self._engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True

    def close(self) -> None:
        self._engine.dispose()


class SqlAlchemyFeedbackExportRepository:
    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine

    def list_feedback_observations(self) -> tuple[FeedbackObservation, ...]:
        statement = (
            select(DocumentRow.sha256, ProcessingJobRow, ReviewDecisionRow)
            .join(ProcessingJobRow, ProcessingJobRow.document_id == DocumentRow.id)
            .join(ReviewDecisionRow, ReviewDecisionRow.job_id == ProcessingJobRow.id)
        )
        with Session(self._engine) as session, session.begin():
            session.execute(text("SET TRANSACTION READ ONLY"))
            rows = session.execute(statement).all()
            return tuple(
                FeedbackObservation(
                    source_sha256=source_sha256,
                    processing_status=job.status,
                    machine_classification=job.predicted_class,
                    final_classification=decision.final_classification,
                    review_outcome=decision.status,
                    model_version=job.model_version,
                    model_evidence=SqlAlchemySubmissionRepository._model_evidence(job),
                )
                for source_sha256, job, decision in rows
            )

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
            if event.event_type.is_completed or event.event_type is ResultEventType.FAILED:
                audit_action = (
                    AuditAction.PROCESSING_COMPLETED
                    if event.event_type.is_completed
                    else AuditAction.PROCESSING_FAILED
                )
                details_version = 2 if event.model_evidence is not None else 1
                details = self._audit_details(event)
                session.add(
                    AuditEventRow(
                        id=uuid5(event.event_id, audit_action.value),
                        action=audit_action.value,
                        actor_principal_id=API_SYSTEM_PRINCIPAL_ID,
                        document_id=event.document_id,
                        job_id=event.job_id,
                        review_id=None,
                        correlation_id=event.correlation_id,
                        causation_id=event.event_id,
                        occurred_at=event.occurred_at,
                        details_version=details_version,
                        details=details,
                    )
                )
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
        if event.event_type.is_completed:
            if event.classification is None or event.confidence is None:
                raise ResultEventInvariantError(code=ResultEventFailureCode.INVALID_EVENT)
            if (
                event.event_type is ResultEventType.COMPLETED_V2 and event.model_evidence is None
            ) or (
                event.event_type is ResultEventType.COMPLETED and event.model_evidence is not None
            ):
                raise ResultEventInvariantError(code=ResultEventFailureCode.INVALID_EVENT)
            job.status = ProcessingStatus.COMPLETED.value
            job.predicted_class = event.classification
            job.confidence = Decimal(str(event.confidence))
            if event.model_evidence is not None:
                evidence = event.model_evidence
                job.dataset_version = evidence.dataset_version
                job.dataset_sha256 = evidence.dataset_sha256
                job.preprocessing_version = evidence.preprocessing_version
                job.pipeline_version = evidence.pipeline_version
                job.artifact_sha256 = evidence.artifact_sha256
                job.evaluation_policy_version = evidence.evaluation_policy_version
                job.evaluation_policy_sha256 = evidence.evaluation_policy_sha256
                job.evaluation_report_sha256 = evidence.evaluation_report_sha256
            return

        if event.failure_code is None:
            raise ResultEventInvariantError(code=ResultEventFailureCode.INVALID_EVENT)
        job.status = ProcessingStatus.FAILED.value
        job.failure_code = event.failure_code

    @staticmethod
    def _audit_details(event: ResultEvent) -> dict[str, object]:
        evidence = event.model_evidence
        if evidence is None:
            return {}
        return {
            "modelEvidenceStatus": "measured",
            "modelVersion": event.model_version,
            "datasetVersion": evidence.dataset_version,
            "datasetSha256": evidence.dataset_sha256,
            "preprocessingVersion": evidence.preprocessing_version,
            "pipelineVersion": evidence.pipeline_version,
            "artifactSha256": evidence.artifact_sha256,
            "evaluationPolicyVersion": evidence.evaluation_policy_version,
            "evaluationPolicySha256": evidence.evaluation_policy_sha256,
            "evaluationReportSha256": evidence.evaluation_report_sha256,
        }
