from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import BinaryIO, Protocol
from uuid import UUID


class ProcessingStatus(StrEnum):
    ACCEPTED = "accepted"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


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
    FAILED = "document.processing.failed.v1"


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


class ProblemCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_DOCUMENT = "INVALID_DOCUMENT"
    DOCUMENT_TOO_LARGE = "DOCUMENT_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
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
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.correlation_id = correlation_id

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
    failure_code: str | None = None


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

    def is_ready(self) -> bool: ...


class SubmissionRepository(Protocol):
    def save(self, submission: DocumentSubmission) -> None: ...

    def observe_submission_commit(
        self, submission: DocumentSubmission
    ) -> SubmissionCommitObservation: ...

    def get_status(self, document_id: UUID) -> DocumentStatusRecord | None: ...

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
