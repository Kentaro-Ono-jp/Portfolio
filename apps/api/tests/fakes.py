from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from reactorfront_api.domain import (
    DocumentStatusRecord,
    DocumentSubmission,
    ProcessingStatus,
    SubmissionCommitObservation,
    SubmissionCommitOutcome,
    SubmissionPersistenceError,
)


@dataclass
class FakeRepository:
    submissions: list[DocumentSubmission] = field(default_factory=list)
    records: dict[UUID, DocumentStatusRecord] = field(default_factory=dict)
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
        self.records[submission.document_id] = DocumentStatusRecord(
            document_id=submission.document_id,
            job_id=submission.job_id,
            status=ProcessingStatus.ACCEPTED,
            created_at=submission.occurred_at,
        )
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

    def get_status(self, document_id: UUID) -> DocumentStatusRecord | None:
        if self.get_error is not None:
            raise self.get_error
        return self.records.get(document_id)

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

    def is_ready(self) -> bool:
        if self.readiness_error is not None:
            raise self.readiness_error
        return self.ready


@dataclass
class FakeValidator:
    payloads: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def validate(self, *, event_type: str, payload: dict[str, object]) -> None:
        self.payloads.append((event_type, payload))
