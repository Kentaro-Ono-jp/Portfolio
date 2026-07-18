from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from reactorfront_api.domain import (
    BinaryDocument,
    DocumentStatusRecord,
    DocumentSubmission,
    EventContractValidator,
    ObjectStorage,
    ProblemCode,
    ProcessingStatus,
    PublicProblem,
    SubmissionCommitState,
    SubmissionPersistenceError,
    SubmissionRepository,
    SubmissionResult,
)

LOGGER = logging.getLogger(__name__)
PDF_CONTENT_TYPE = "application/pdf"
PDF_SIGNATURE = b"%PDF-"
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024
REQUESTED_EVENT_TYPE = "document.processing.requested.v1"


class DocumentService:
    def __init__(
        self,
        *,
        repository: SubmissionRepository,
        object_storage: ObjectStorage,
        event_validator: EventContractValidator,
        id_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._object_storage = object_storage
        self._event_validator = event_validator
        self._id_factory = id_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def submit(
        self,
        *,
        stream: BinaryDocument,
        original_filename: str | None,
        content_type: str | None,
        correlation_id: UUID,
    ) -> SubmissionResult:
        normalized_content_type = (content_type or "").split(";", maxsplit=1)[0].strip().lower()
        if normalized_content_type != PDF_CONTENT_TYPE:
            raise PublicProblem(
                status=415,
                code=ProblemCode.UNSUPPORTED_MEDIA_TYPE,
                title="Unsupported media type",
                detail="The uploaded file must use application/pdf.",
                correlation_id=correlation_id,
            )

        content = self._read_limited(stream=stream, correlation_id=correlation_id)
        if not content.startswith(PDF_SIGNATURE):
            raise PublicProblem(
                status=400,
                code=ProblemCode.INVALID_DOCUMENT,
                title="Invalid document",
                detail="The uploaded file does not have a valid PDF signature.",
                correlation_id=correlation_id,
            )

        document_id = self._id_factory()
        job_id = self._id_factory()
        event_id = self._id_factory()
        occurred_at = self._clock().astimezone(UTC)
        digest = hashlib.sha256(content).hexdigest()
        object_key = f"documents/{document_id}/source.pdf"
        event_payload: dict[str, object] = {
            "eventId": str(event_id),
            "eventType": REQUESTED_EVENT_TYPE,
            "occurredAt": occurred_at.isoformat().replace("+00:00", "Z"),
            "correlationId": str(correlation_id),
            "documentId": str(document_id),
            "jobId": str(job_id),
            "objectKey": object_key,
            "sourceSha256": digest,
        }
        self._event_validator.validate(event_type=REQUESTED_EVENT_TYPE, payload=event_payload)

        submission = DocumentSubmission(
            document_id=document_id,
            job_id=job_id,
            event_id=event_id,
            correlation_id=correlation_id,
            original_filename=self._display_filename(original_filename),
            object_key=object_key,
            sha256=digest,
            content_type=PDF_CONTENT_TYPE,
            size_bytes=len(content),
            occurred_at=occurred_at,
            event_payload=event_payload,
        )

        try:
            self._object_storage.put(
                object_key=object_key,
                content=content,
                content_type=PDF_CONTENT_TYPE,
                sha256=digest,
            )
        except Exception as error:
            LOGGER.exception(
                "Object upload failed",
                extra={"correlation_id": str(correlation_id), "document_id": str(document_id)},
            )
            raise self._dependency_problem(correlation_id) from error

        try:
            self._repository.save(submission)
        except SubmissionPersistenceError as error:
            LOGGER.exception(
                "Submission transaction failed",
                extra={"correlation_id": str(correlation_id), "document_id": str(document_id)},
            )
            commit_state = error.commit_state
            if commit_state is SubmissionCommitState.UNKNOWN:
                commit_state = self._resolve_commit_state(
                    submission=submission,
                    correlation_id=correlation_id,
                )
            if commit_state is SubmissionCommitState.COMMITTED:
                LOGGER.warning(
                    "Submission commit succeeded but its acknowledgement was lost",
                    extra={
                        "correlation_id": str(correlation_id),
                        "document_id": str(document_id),
                        "job_id": str(job_id),
                    },
                )
                return self._submission_result(document_id=document_id, job_id=job_id)
            if commit_state is SubmissionCommitState.NOT_COMMITTED:
                self._compensate_object(object_key=object_key, correlation_id=correlation_id)
            else:
                LOGGER.error(
                    "Source object retained because submission commit state is unresolved",
                    extra={
                        "correlation_id": str(correlation_id),
                        "document_id": str(document_id),
                        "job_id": str(job_id),
                        "object_key": object_key,
                    },
                )
            raise self._dependency_problem(correlation_id) from error
        except Exception as error:
            LOGGER.exception(
                "Unexpected submission repository failure; source object retained",
                extra={"correlation_id": str(correlation_id), "document_id": str(document_id)},
            )
            raise self._dependency_problem(correlation_id) from error

        return self._submission_result(document_id=document_id, job_id=job_id)

    @staticmethod
    def _submission_result(*, document_id: UUID, job_id: UUID) -> SubmissionResult:
        return SubmissionResult(
            document_id=document_id,
            job_id=job_id,
            status=ProcessingStatus.ACCEPTED,
        )

    def get_status(self, *, document_id: UUID, correlation_id: UUID) -> DocumentStatusRecord:
        try:
            result = self._repository.get_status(document_id)
        except Exception as error:
            LOGGER.exception(
                "Document lookup failed",
                extra={"correlation_id": str(correlation_id), "document_id": str(document_id)},
            )
            raise self._dependency_problem(correlation_id) from error

        if result is None:
            raise PublicProblem(
                status=404,
                code=ProblemCode.DOCUMENT_NOT_FOUND,
                title="Document not found",
                detail="No document exists for the supplied identifier.",
                correlation_id=correlation_id,
            )
        return result

    def is_ready(self) -> bool:
        try:
            return self._repository.is_ready() and self._object_storage.is_ready()
        except Exception:
            LOGGER.exception("Dependency readiness check failed")
            return False

    def close(self) -> None:
        self._repository.close()

    @staticmethod
    def _read_limited(*, stream: BinaryDocument, correlation_id: UUID) -> bytes:
        chunks: list[bytes] = []
        size = 0
        while chunk := stream.read(READ_CHUNK_BYTES):
            size += len(chunk)
            if size > MAX_DOCUMENT_BYTES:
                raise PublicProblem(
                    status=413,
                    code=ProblemCode.DOCUMENT_TOO_LARGE,
                    title="Document too large",
                    detail="The uploaded file exceeds the 5 MiB limit.",
                    correlation_id=correlation_id,
                )
            chunks.append(chunk)
        return b"".join(chunks)

    @staticmethod
    def _display_filename(filename: str | None) -> str:
        candidate = (filename or "document.pdf").replace("\\", "/")
        basename = PurePosixPath(candidate).name
        printable = "".join(character for character in basename if character.isprintable())
        normalized = printable.strip()[:255]
        return normalized or "document.pdf"

    def _compensate_object(self, *, object_key: str, correlation_id: UUID) -> None:
        try:
            self._object_storage.delete(object_key=object_key)
        except Exception:
            LOGGER.exception(
                "Object compensation failed",
                extra={"correlation_id": str(correlation_id), "object_key": object_key},
            )

    def _resolve_commit_state(
        self,
        *,
        submission: DocumentSubmission,
        correlation_id: UUID,
    ) -> SubmissionCommitState:
        try:
            return self._repository.get_submission_commit_state(submission)
        except Exception:
            LOGGER.exception(
                "Submission commit state could not be reconciled",
                extra={
                    "correlation_id": str(correlation_id),
                    "document_id": str(submission.document_id),
                    "job_id": str(submission.job_id),
                },
            )
            return SubmissionCommitState.UNKNOWN

    @staticmethod
    def _dependency_problem(correlation_id: UUID) -> PublicProblem:
        return PublicProblem(
            status=503,
            code=ProblemCode.DEPENDENCY_UNAVAILABLE,
            title="Dependency unavailable",
            detail="A required service is temporarily unavailable.",
            correlation_id=correlation_id,
        )
