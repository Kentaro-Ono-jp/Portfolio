from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import BinaryIO, Protocol
from uuid import UUID


class ProcessingStatus(StrEnum):
    ACCEPTED = "accepted"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class SubmissionCommitState(StrEnum):
    COMMITTED = "committed"
    NOT_COMMITTED = "not_committed"
    UNKNOWN = "unknown"
    INCONSISTENT = "inconsistent"


class SubmissionPersistenceError(Exception):
    def __init__(self, *, commit_state: SubmissionCommitState) -> None:
        super().__init__(f"Submission persistence failed with state {commit_state.value}")
        self.commit_state = commit_state


class ProblemCode(StrEnum):
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

    def get_submission_commit_state(
        self, submission: DocumentSubmission
    ) -> SubmissionCommitState: ...

    def get_status(self, document_id: UUID) -> DocumentStatusRecord | None: ...

    def is_ready(self) -> bool: ...

    def close(self) -> None: ...


class EventContractValidator(Protocol):
    def validate(self, *, event_type: str, payload: dict[str, object]) -> None: ...


BinaryDocument = BinaryIO | ReadableUpload
