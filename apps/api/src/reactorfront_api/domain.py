from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import BinaryIO, Protocol
from uuid import UUID


class ProcessingStatus(StrEnum):
    ACCEPTED = "accepted"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PrincipalKind(StrEnum):
    OIDC = "oidc"
    SYSTEM = "system"


class ReviewStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    APPROVED = "approved"
    CORRECTED = "corrected"


class AuditAction(StrEnum):
    DOCUMENT_SUBMITTED = "document.submitted"
    PROCESSING_COMPLETED = "processing.completed"
    PROCESSING_FAILED = "processing.failed"
    REVIEW_APPROVED = "review.approved"
    REVIEW_CORRECTED = "review.corrected"


class ReviewOperationFailureCode(StrEnum):
    DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    REVIEW_NOT_AVAILABLE = "REVIEW_NOT_AVAILABLE"


class SubmissionCommitOutcome(StrEnum):
    NOT_COMMITTED = "not_committed"
    UNKNOWN = "unknown"


class SubmissionCommitObservation(StrEnum):
    COMMITTED = "committed"
    ABSENT = "absent"
    INCONSISTENT = "inconsistent"


class PublishFailureCode(StrEnum):
    BROKER_UNAVAILABLE = "BROKER_UNAVAILABLE"
    CONFIRM_NACK = "CONFIRM_NACK"
    CONFIRM_TIMEOUT = "CONFIRM_TIMEOUT"
    FINALIZE_FAILED = "FINALIZE_FAILED"
    INVARIANT_VIOLATION = "INVARIANT_VIOLATION"
    PUBLISH_UNKNOWN = "PUBLISH_UNKNOWN"
    UNROUTABLE = "UNROUTABLE"


class PublishFinalizeResult(StrEnum):
    PUBLISHED = "published"
    ALREADY_PUBLISHED = "already_published"
    LEASE_LOST = "lease_lost"


class ResultEventType(StrEnum):
    STARTED = "document.processing.started.v1"
    COMPLETED = "document.processing.completed.v1"
    COMPLETED_V2 = "document.processing.completed.v2"
    FAILED = "document.processing.failed.v1"

    @property
    def is_completed(self) -> bool:
        return self in {ResultEventType.COMPLETED, ResultEventType.COMPLETED_V2}


class ResultApplyOutcome(StrEnum):
    APPLIED = "applied"
    DUPLICATE = "duplicate"
    DEFERRED = "deferred"


class ResultEventFailureCode(StrEnum):
    EVENT_ID_REUSE = "EVENT_ID_REUSE"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    INVALID_EVENT = "INVALID_EVENT"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    TERMINAL_CONFLICT = "TERMINAL_CONFLICT"


class OutboxInvariantError(Exception):
    pass


class OutboxPublishError(Exception):
    def __init__(self, *, code: PublishFailureCode) -> None:
        super().__init__(code.value)
        self.code = code


class InvalidResultEvent(Exception):
    pass


class ResultEventInvariantError(Exception):
    def __init__(self, *, code: ResultEventFailureCode) -> None:
        super().__init__(code.value)
        self.code = code


class SubmissionPersistenceError(Exception):
    def __init__(self, *, commit_outcome: SubmissionCommitOutcome) -> None:
        super().__init__(f"Submission persistence failed with outcome {commit_outcome.value}")
        self.commit_outcome = commit_outcome


class ReviewOperationError(Exception):
    def __init__(self, *, code: ReviewOperationFailureCode) -> None:
        super().__init__(code.value)
        self.code = code


class ProblemCode(StrEnum):
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    INSUFFICIENT_CAPABILITY = "INSUFFICIENT_CAPABILITY"
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_DOCUMENT = "INVALID_DOCUMENT"
    DOCUMENT_TOO_LARGE = "DOCUMENT_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    PRECONDITION_REQUIRED = "PRECONDITION_REQUIRED"
    REVIEW_NOT_AVAILABLE = "REVIEW_NOT_AVAILABLE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"


class PublicProblem(Exception):
    def __init__(
        self,
        *,
        status: int,
        code: ProblemCode,
        title: str,
        detail: str,
        correlation_id: UUID,
        response_headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.correlation_id = correlation_id
        self.response_headers = dict(response_headers or {})

    @property
    def type_uri(self) -> str:
        slug = self.code.value.lower().replace("_", "-")
        return f"urn:reactorfront:problem:{slug}"


@dataclass(frozen=True, slots=True)
class DocumentSubmission:
    document_id: UUID
    job_id: UUID
    event_id: UUID
    correlation_id: UUID
    submitted_by_principal_id: UUID
    original_filename: str
    object_key: str
    sha256: str
    content_type: str
    size_bytes: int
    occurred_at: datetime
    event_payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class SubmissionResult:
    document_id: UUID
    job_id: UUID
    status: ProcessingStatus


@dataclass(frozen=True, slots=True)
class MeasuredModelEvidence:
    dataset_version: str
    dataset_sha256: str
    preprocessing_version: str
    pipeline_version: str
    artifact_sha256: str
    evaluation_policy_version: str
    evaluation_policy_sha256: str
    evaluation_report_sha256: str


@dataclass(frozen=True, slots=True)
class DocumentStatusRecord:
    document_id: UUID
    job_id: UUID
    status: ProcessingStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    predicted_class: str | None = None
    confidence: float | None = None
    model_version: str | None = None
    model_evidence: MeasuredModelEvidence | None = None
    failure_code: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentSourceRecord:
    document_id: UUID
    original_filename: str
    object_key: str
    sha256: str
    content_type: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class DocumentSource:
    document_id: UUID
    filename: str
    content: bytes
    content_type: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class StoredObject:
    content: bytes
    content_type: str
    size_bytes: int
    sha256: str | None


@dataclass(frozen=True, slots=True)
class PrincipalRecord:
    principal_id: UUID
    kind: PrincipalKind
    issuer: str | None
    subject: str | None
    system_key: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ReviewRecord:
    document_id: UUID
    job_id: UUID
    status: ReviewStatus
    machine_classification: str
    machine_confidence: Decimal
    model_version: str
    review_version: int
    model_evidence: MeasuredModelEvidence | None = None
    review_id: UUID | None = None
    final_classification: str | None = None
    reviewer_principal_id: UUID | None = None
    decided_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ReviewCommand:
    document_id: UUID
    principal_id: UUID
    correlation_id: UUID
    final_classification: str
    if_match: str
    idempotency_key: UUID
    request_digest: str
    decision_id: UUID
    decided_at: datetime


@dataclass(frozen=True, slots=True)
class AuditEventRecord:
    event_id: UUID
    action: AuditAction
    occurred_at: datetime
    actor_principal_id: UUID
    document_id: UUID
    job_id: UUID
    correlation_id: UUID
    details_version: int
    details: dict[str, object]
    review_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class AuditHistory:
    document_id: UUID
    events: tuple[AuditEventRecord, ...]


def review_entity_tag(record: ReviewRecord) -> str:
    confidence = format(record.machine_confidence.normalize(), "f")
    evidence = record.model_evidence
    evidence_identity = (
        ("legacy-unmeasured",)
        if evidence is None
        else (
            "measured",
            evidence.dataset_version,
            evidence.dataset_sha256,
            evidence.preprocessing_version,
            evidence.pipeline_version,
            evidence.artifact_sha256,
            evidence.evaluation_policy_version,
            evidence.evaluation_policy_sha256,
            evidence.evaluation_report_sha256,
        )
    )
    identity = "\x1f".join(
        (
            str(record.document_id),
            str(record.job_id),
            record.status.value,
            record.machine_classification,
            confidence,
            record.model_version,
            *evidence_identity,
            str(record.review_version),
            str(record.review_id or ""),
            record.final_classification or "",
            str(record.reviewer_principal_id or ""),
        )
    )
    return f'"{hashlib.sha256(identity.encode("utf-8")).hexdigest()}"'


@dataclass(frozen=True, slots=True)
class OutboxLease:
    event_id: UUID
    event_type: str
    job_id: UUID
    payload: dict[str, object]
    created_at: datetime
    lease_owner: str
    leased_until: datetime
    attempt_count: int


@dataclass(frozen=True, slots=True)
class ResultEvent:
    event_id: UUID
    event_type: ResultEventType
    occurred_at: datetime
    correlation_id: UUID
    document_id: UUID
    job_id: UUID
    object_key: str
    source_sha256: str
    model_version: str
    logical_payload_sha256: str
    model_evidence: MeasuredModelEvidence | None = None
    classification: str | None = None
    confidence: float | None = None
    failure_code: str | None = None


class ReadableUpload(Protocol):
    def read(self, size: int = -1) -> bytes: ...


class ObjectStorage(Protocol):
    def put(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str,
        sha256: str,
    ) -> None: ...

    def delete(self, *, object_key: str) -> None: ...

    def get(self, *, object_key: str, maximum_bytes: int) -> StoredObject: ...

    def is_ready(self) -> bool: ...


class SubmissionRepository(Protocol):
    def save(self, submission: DocumentSubmission) -> None: ...

    def observe_submission_commit(
        self, submission: DocumentSubmission
    ) -> SubmissionCommitObservation: ...

    def get_status(self, document_id: UUID, principal_id: UUID) -> DocumentStatusRecord | None: ...

    def get_source(self, document_id: UUID, principal_id: UUID) -> DocumentSourceRecord | None: ...

    def get_review(self, document_id: UUID, principal_id: UUID) -> ReviewRecord | None: ...

    def submit_review(self, command: ReviewCommand) -> ReviewRecord: ...

    def get_audit_history(self, document_id: UUID, principal_id: UUID) -> AuditHistory | None: ...

    def is_ready(self) -> bool: ...

    def close(self) -> None: ...


class EventContractValidator(Protocol):
    def validate(self, *, event_type: str, payload: dict[str, object]) -> None: ...


class ReadinessProbe(Protocol):
    def is_ready(self) -> bool: ...


class OutboxRepository(Protocol):
    def lease_pending(
        self,
        *,
        lease_owner: str,
        lease_duration: timedelta,
        batch_size: int,
    ) -> list[OutboxLease]: ...

    def mark_published(
        self,
        *,
        event_id: UUID,
        lease_owner: str,
        attempt_count: int,
    ) -> PublishFinalizeResult: ...

    def record_failure(
        self,
        *,
        event_id: UUID,
        lease_owner: str,
        attempt_count: int,
        code: PublishFailureCode,
        retry_delay: timedelta,
    ) -> bool: ...

    def is_ready(self) -> bool: ...

    def close(self) -> None: ...


class OutboxPublisher(Protocol):
    def publish(self, lease: OutboxLease) -> None: ...

    def is_ready(self) -> bool: ...


class ResultEventRepository(Protocol):
    def apply(self, event: ResultEvent) -> ResultApplyOutcome: ...

    def is_ready(self) -> bool: ...

    def close(self) -> None: ...


BinaryDocument = BinaryIO | ReadableUpload
