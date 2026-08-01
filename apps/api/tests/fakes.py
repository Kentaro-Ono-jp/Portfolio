from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid5

from reactorfront_api.authentication import Capability, authentication_problem
from reactorfront_api.domain import (
    AuditAction,
    AuditEventRecord,
    AuditHistory,
    DocumentSourceRecord,
    DocumentStatusRecord,
    DocumentSubmission,
    PrincipalKind,
    PrincipalRecord,
    ProcessingStatus,
    ReviewCommand,
    ReviewOperationError,
    ReviewOperationFailureCode,
    ReviewRecord,
    ReviewStatus,
    StoredObject,
    SubmissionCommitObservation,
    SubmissionCommitOutcome,
    SubmissionPersistenceError,
    review_entity_tag,
)


@dataclass
class FakeReadinessProbe:
    ready: bool = True
    error: Exception | None = None
    calls: int = 0

    def is_ready(self) -> bool:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.ready


@dataclass
class FakeRepository:
    submissions: list[DocumentSubmission] = field(default_factory=list)
    records: dict[UUID, DocumentStatusRecord] = field(default_factory=dict)
    owners: dict[UUID, UUID] = field(default_factory=dict)
    sources: dict[UUID, DocumentSourceRecord] = field(default_factory=dict)
    reviews: dict[UUID, ReviewRecord] = field(default_factory=dict)
    audit_events: dict[UUID, list[AuditEventRecord]] = field(default_factory=dict)
    idempotency_records: dict[tuple[UUID, UUID], tuple[UUID, str, ReviewRecord]] = field(
        default_factory=dict
    )
    ready: bool = True
    save_error: Exception | None = None
    commit_acknowledgement_error: Exception | None = None
    commit_observation_error: Exception | None = None
    commit_observation_override: SubmissionCommitObservation | None = None
    get_error: Exception | None = None
    closed: bool = False

    def save(self, submission: DocumentSubmission) -> None:
        if self.save_error is not None:
            raise SubmissionPersistenceError(
                commit_outcome=SubmissionCommitOutcome.NOT_COMMITTED
            ) from self.save_error
        self.submissions.append(submission)
        self.owners[submission.document_id] = submission.submitted_by_principal_id
        self.records[submission.document_id] = DocumentStatusRecord(
            document_id=submission.document_id,
            job_id=submission.job_id,
            status=ProcessingStatus.ACCEPTED,
            created_at=submission.occurred_at,
        )
        self.sources[submission.document_id] = DocumentSourceRecord(
            document_id=submission.document_id,
            original_filename=submission.original_filename,
            object_key=submission.object_key,
            sha256=submission.sha256,
            content_type=submission.content_type,
            size_bytes=submission.size_bytes,
        )
        self.audit_events[submission.document_id] = [
            AuditEventRecord(
                event_id=uuid5(submission.event_id, AuditAction.DOCUMENT_SUBMITTED.value),
                action=AuditAction.DOCUMENT_SUBMITTED,
                occurred_at=submission.occurred_at,
                actor_principal_id=submission.submitted_by_principal_id,
                document_id=submission.document_id,
                job_id=submission.job_id,
                correlation_id=submission.correlation_id,
                details_version=1,
                details={},
            )
        ]
        if self.commit_acknowledgement_error is not None:
            raise SubmissionPersistenceError(
                commit_outcome=SubmissionCommitOutcome.UNKNOWN
            ) from self.commit_acknowledgement_error

    def observe_submission_commit(
        self, submission: DocumentSubmission
    ) -> SubmissionCommitObservation:
        if self.commit_observation_error is not None:
            raise self.commit_observation_error
        if self.commit_observation_override is not None:
            return self.commit_observation_override
        if submission in self.submissions and submission.document_id in self.records:
            return SubmissionCommitObservation.COMMITTED
        return SubmissionCommitObservation.ABSENT

    def get_status(self, document_id: UUID, principal_id: UUID) -> DocumentStatusRecord | None:
        if self.get_error is not None:
            raise self.get_error
        if self.owners.get(document_id) != principal_id:
            return None
        return self.records.get(document_id)

    def get_source(self, document_id: UUID, principal_id: UUID) -> DocumentSourceRecord | None:
        if self.get_error is not None:
            raise self.get_error
        if self.owners.get(document_id) != principal_id:
            return None
        return self.sources.get(document_id)

    def get_review(self, document_id: UUID, principal_id: UUID) -> ReviewRecord | None:
        if self.get_error is not None:
            raise self.get_error
        if self.owners.get(document_id) != principal_id:
            return None
        if document_id in self.reviews:
            return self.reviews[document_id]
        status = self.records.get(document_id)
        if (
            status is None
            or status.status is not ProcessingStatus.COMPLETED
            or status.predicted_class not in {"invoice", "report"}
            or status.confidence is None
            or status.model_version is None
        ):
            raise ReviewOperationError(code=ReviewOperationFailureCode.REVIEW_NOT_AVAILABLE)
        return ReviewRecord(
            document_id=document_id,
            job_id=status.job_id,
            status=ReviewStatus.UNREVIEWED,
            machine_classification=status.predicted_class,
            machine_confidence=Decimal(str(status.confidence)),
            model_version=status.model_version,
            review_version=0,
        )

    def submit_review(self, command: ReviewCommand) -> ReviewRecord:
        current = self.get_review(command.document_id, command.principal_id)
        if current is None:
            raise ReviewOperationError(code=ReviewOperationFailureCode.DOCUMENT_NOT_FOUND)
        key = (command.principal_id, command.idempotency_key)
        existing_receipt = self.idempotency_records.get(key)
        if existing_receipt is not None:
            target, digest, record = existing_receipt
            if target != command.document_id or digest != command.request_digest:
                raise ReviewOperationError(code=ReviewOperationFailureCode.IDEMPOTENCY_CONFLICT)
            return record
        if current.status is not ReviewStatus.UNREVIEWED:
            raise ReviewOperationError(code=ReviewOperationFailureCode.REVIEW_NOT_AVAILABLE)
        if command.if_match != review_entity_tag(current):
            raise ReviewOperationError(code=ReviewOperationFailureCode.PRECONDITION_FAILED)
        review_status = (
            ReviewStatus.APPROVED
            if command.final_classification == current.machine_classification
            else ReviewStatus.CORRECTED
        )
        record = ReviewRecord(
            document_id=current.document_id,
            job_id=current.job_id,
            status=review_status,
            machine_classification=current.machine_classification,
            machine_confidence=current.machine_confidence,
            model_version=current.model_version,
            review_version=1,
            review_id=command.decision_id,
            final_classification=command.final_classification,
            reviewer_principal_id=command.principal_id,
            decided_at=command.decided_at,
        )
        self.reviews[command.document_id] = record
        self.idempotency_records[key] = (
            command.document_id,
            command.request_digest,
            record,
        )
        action = (
            AuditAction.REVIEW_APPROVED
            if review_status is ReviewStatus.APPROVED
            else AuditAction.REVIEW_CORRECTED
        )
        self.audit_events.setdefault(command.document_id, []).append(
            AuditEventRecord(
                event_id=uuid5(command.decision_id, action.value),
                action=action,
                occurred_at=command.decided_at,
                actor_principal_id=command.principal_id,
                document_id=command.document_id,
                job_id=current.job_id,
                review_id=command.decision_id,
                correlation_id=command.correlation_id,
                details_version=1,
                details={},
            )
        )
        return record

    def get_audit_history(
        self,
        document_id: UUID,
        principal_id: UUID,
    ) -> AuditHistory | None:
        if self.get_error is not None:
            raise self.get_error
        if self.owners.get(document_id) != principal_id:
            return None
        return AuditHistory(
            document_id=document_id,
            events=tuple(
                sorted(
                    self.audit_events.get(document_id, []),
                    key=lambda event: (event.occurred_at, event.event_id),
                )
            ),
        )

    def is_ready(self) -> bool:
        return self.ready

    def close(self) -> None:
        self.closed = True


@dataclass
class FakeStorage:
    objects: dict[str, tuple[bytes, str, str]] = field(default_factory=dict)
    deleted: list[str] = field(default_factory=list)
    ready: bool = True
    put_error: Exception | None = None
    delete_error: Exception | None = None
    readiness_error: Exception | None = None
    get_error: Exception | None = None

    def put(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str,
        sha256: str,
    ) -> None:
        if self.put_error is not None:
            raise self.put_error
        self.objects[object_key] = (content, content_type, sha256)

    def delete(self, *, object_key: str) -> None:
        if self.delete_error is not None:
            raise self.delete_error
        self.deleted.append(object_key)
        self.objects.pop(object_key, None)

    def get(self, *, object_key: str, maximum_bytes: int) -> StoredObject:
        if self.get_error is not None:
            raise self.get_error
        content, content_type, sha256 = self.objects[object_key]
        if len(content) > maximum_bytes:
            raise ValueError("object too large")
        return StoredObject(
            content=content,
            content_type=content_type,
            size_bytes=len(content),
            sha256=sha256,
        )

    def is_ready(self) -> bool:
        if self.readiness_error is not None:
            raise self.readiness_error
        return self.ready


@dataclass
class FakeValidator:
    payloads: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def validate(self, *, event_type: str, payload: dict[str, object]) -> None:
        self.payloads.append((event_type, payload))


@dataclass
class FakeRequestAuthorizer:
    principal_id: UUID
    expected_token: str = "synthetic-access-token"
    calls: list[tuple[str | None, object]] = field(default_factory=list)
    closed: bool = False

    def authorize(
        self,
        *,
        authorization_header: str | None,
        capability: Capability,
        correlation_id: UUID,
    ) -> PrincipalRecord:
        self.calls.append((authorization_header, capability))
        if authorization_header != f"Bearer {self.expected_token}":
            raise authentication_problem(correlation_id)
        return PrincipalRecord(
            principal_id=self.principal_id,
            kind=PrincipalKind.OIDC,
            issuer="https://identity.example.invalid/dex",
            subject="synthetic-reviewer",
            system_key=None,
            created_at=datetime(2026, 7, 31, tzinfo=UTC),
        )

    def close(self) -> None:
        self.closed = True
