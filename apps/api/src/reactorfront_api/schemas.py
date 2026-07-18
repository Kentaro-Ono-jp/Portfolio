from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from reactorfront_api.domain import DocumentStatusRecord, ProcessingStatus


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class DocumentAcceptedResponse(ApiModel):
    document_id: UUID = Field(alias="documentId")
    job_id: UUID = Field(alias="jobId")
    status: Literal[ProcessingStatus.ACCEPTED]


class StatusIdentity(ApiModel):
    document_id: UUID = Field(alias="documentId")
    job_id: UUID = Field(alias="jobId")
    created_at: datetime = Field(alias="createdAt")


class AcceptedDocumentStatusResponse(StatusIdentity):
    status: Literal[ProcessingStatus.ACCEPTED]


class QueuedDocumentStatusResponse(StatusIdentity):
    status: Literal[ProcessingStatus.QUEUED]


class ProcessingDocumentStatusResponse(StatusIdentity):
    status: Literal[ProcessingStatus.PROCESSING]
    started_at: datetime = Field(alias="startedAt")


class CompletedDocumentStatusResponse(StatusIdentity):
    status: Literal[ProcessingStatus.COMPLETED]
    classification: Literal["invoice", "report"]
    confidence: float = Field(ge=0, le=1)
    model_version: str = Field(alias="modelVersion", min_length=1, max_length=128)
    started_at: datetime = Field(alias="startedAt")
    completed_at: datetime = Field(alias="completedAt")


class FailedDocumentStatusResponse(StatusIdentity):
    status: Literal[ProcessingStatus.FAILED]
    failure_code: str = Field(alias="failureCode", pattern=r"^[A-Z][A-Z0-9_]*$", max_length=128)
    started_at: datetime | None = Field(default=None, alias="startedAt")
    completed_at: datetime = Field(alias="completedAt")


DocumentStatusResponse = Annotated[
    AcceptedDocumentStatusResponse
    | QueuedDocumentStatusResponse
    | ProcessingDocumentStatusResponse
    | CompletedDocumentStatusResponse
    | FailedDocumentStatusResponse,
    Field(discriminator="status"),
]


class HealthResponse(ApiModel):
    status: Literal["ok"] = "ok"


class ProblemResponse(ApiModel):
    type: str
    title: str
    status: int = Field(ge=400, le=599)
    detail: str
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    correlation_id: UUID = Field(alias="correlationId")


def serialize_document_status(record: DocumentStatusRecord) -> DocumentStatusResponse:
    match record.status:
        case ProcessingStatus.ACCEPTED:
            return AcceptedDocumentStatusResponse(
                documentId=record.document_id,
                jobId=record.job_id,
                createdAt=record.created_at,
                status=ProcessingStatus.ACCEPTED,
            )
        case ProcessingStatus.QUEUED:
            return QueuedDocumentStatusResponse(
                documentId=record.document_id,
                jobId=record.job_id,
                createdAt=record.created_at,
                status=ProcessingStatus.QUEUED,
            )
        case ProcessingStatus.PROCESSING:
            if record.started_at is None:
                raise ValueError("A processing job must have started_at")
            return ProcessingDocumentStatusResponse(
                documentId=record.document_id,
                jobId=record.job_id,
                createdAt=record.created_at,
                status=ProcessingStatus.PROCESSING,
                startedAt=record.started_at,
            )
        case ProcessingStatus.COMPLETED:
            if (
                record.started_at is None
                or record.completed_at is None
                or record.predicted_class is None
                or record.confidence is None
                or record.model_version is None
                or record.predicted_class not in {"invoice", "report"}
            ):
                raise ValueError("A completed job must have a complete result")
            classification = cast(Literal["invoice", "report"], record.predicted_class)
            return CompletedDocumentStatusResponse(
                documentId=record.document_id,
                jobId=record.job_id,
                createdAt=record.created_at,
                status=ProcessingStatus.COMPLETED,
                classification=classification,
                confidence=record.confidence,
                modelVersion=record.model_version,
                startedAt=record.started_at,
                completedAt=record.completed_at,
            )
        case ProcessingStatus.FAILED:
            if record.completed_at is None or record.failure_code is None:
                raise ValueError("A failed job must have completion data")
            return FailedDocumentStatusResponse(
                documentId=record.document_id,
                jobId=record.job_id,
                createdAt=record.created_at,
                status=ProcessingStatus.FAILED,
                failureCode=record.failure_code,
                startedAt=record.started_at,
                completedAt=record.completed_at,
            )
