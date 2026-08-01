from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from reactorfront_api.domain import (
    AuditHistory,
    DocumentStatusRecord,
    ProcessingStatus,
    ReviewRecord,
    ReviewStatus,
)


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


class ReviewDecisionRequest(ApiModel):
    final_classification: Literal["invoice", "report"] = Field(alias="finalClassification")


class ReviewResponse(ApiModel):
    document_id: UUID = Field(alias="documentId")
    job_id: UUID = Field(alias="jobId")
    status: Literal["unreviewed", "approved", "corrected"]
    machine_classification: Literal["invoice", "report"] = Field(alias="machineClassification")
    machine_confidence: float = Field(alias="machineConfidence", ge=0, le=1)
    model_version: str = Field(alias="modelVersion", min_length=1, max_length=128)
    review_version: int = Field(alias="reviewVersion", ge=0)
    final_classification: Literal["invoice", "report"] | None = Field(
        default=None,
        alias="finalClassification",
    )
    reviewer_principal_id: UUID | None = Field(default=None, alias="reviewerPrincipalId")
    decided_at: datetime | None = Field(default=None, alias="decidedAt")


class AuditEventResponse(ApiModel):
    event_id: UUID = Field(alias="eventId")
    action: Literal[
        "document.submitted",
        "processing.completed",
        "processing.failed",
        "review.approved",
        "review.corrected",
    ]
    occurred_at: datetime = Field(alias="occurredAt")
    actor_principal_id: UUID = Field(alias="actorPrincipalId")
    document_id: UUID = Field(alias="documentId")
    job_id: UUID = Field(alias="jobId")
    review_id: UUID | None = Field(default=None, alias="reviewId")
    correlation_id: UUID = Field(alias="correlationId")
    details_version: Literal[1] = Field(alias="detailsVersion")
    details: dict[str, object]


class AuditHistoryResponse(ApiModel):
    document_id: UUID = Field(alias="documentId")
    events: list[AuditEventResponse]


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
                document_id=record.document_id,
                job_id=record.job_id,
                created_at=record.created_at,
                status=ProcessingStatus.ACCEPTED,
            )
        case ProcessingStatus.QUEUED:
            return QueuedDocumentStatusResponse(
                document_id=record.document_id,
                job_id=record.job_id,
                created_at=record.created_at,
                status=ProcessingStatus.QUEUED,
            )
        case ProcessingStatus.PROCESSING:
            if record.started_at is None:
                raise ValueError("A processing job must have started_at")
            return ProcessingDocumentStatusResponse(
                document_id=record.document_id,
                job_id=record.job_id,
                created_at=record.created_at,
                status=ProcessingStatus.PROCESSING,
                started_at=record.started_at,
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
                document_id=record.document_id,
                job_id=record.job_id,
                created_at=record.created_at,
                status=ProcessingStatus.COMPLETED,
                classification=classification,
                confidence=record.confidence,
                model_version=record.model_version,
                started_at=record.started_at,
                completed_at=record.completed_at,
            )
        case ProcessingStatus.FAILED:
            if record.completed_at is None or record.failure_code is None:
                raise ValueError("A failed job must have completion data")
            return FailedDocumentStatusResponse(
                document_id=record.document_id,
                job_id=record.job_id,
                created_at=record.created_at,
                status=ProcessingStatus.FAILED,
                failure_code=record.failure_code,
                started_at=record.started_at,
                completed_at=record.completed_at,
            )


def serialize_review(record: ReviewRecord) -> ReviewResponse:
    if record.machine_classification not in {"invoice", "report"}:
        raise ValueError("A review must have a supported machine classification")
    machine_classification = cast(
        Literal["invoice", "report"],
        record.machine_classification,
    )
    if record.status is ReviewStatus.UNREVIEWED:
        if (
            record.review_version != 0
            or record.review_id is not None
            or record.final_classification is not None
            or record.reviewer_principal_id is not None
            or record.decided_at is not None
        ):
            raise ValueError("An unreviewed representation cannot contain a decision")
        return ReviewResponse(
            document_id=record.document_id,
            job_id=record.job_id,
            status=ReviewStatus.UNREVIEWED,
            machine_classification=machine_classification,
            machine_confidence=float(record.machine_confidence),
            model_version=record.model_version,
            review_version=0,
        )

    if (
        record.review_version < 1
        or record.review_id is None
        or record.final_classification not in {"invoice", "report"}
        or record.reviewer_principal_id is None
        or record.decided_at is None
    ):
        raise ValueError("A terminal review must have complete decision evidence")
    final_classification = cast(
        Literal["invoice", "report"],
        record.final_classification,
    )
    return ReviewResponse(
        document_id=record.document_id,
        job_id=record.job_id,
        status=record.status,
        machine_classification=machine_classification,
        machine_confidence=float(record.machine_confidence),
        model_version=record.model_version,
        review_version=record.review_version,
        final_classification=final_classification,
        reviewer_principal_id=record.reviewer_principal_id,
        decided_at=record.decided_at,
    )


def serialize_audit_history(history: AuditHistory) -> AuditHistoryResponse:
    return AuditHistoryResponse(
        document_id=history.document_id,
        events=[
            AuditEventResponse(
                event_id=event.event_id,
                action=event.action,
                occurred_at=event.occurred_at,
                actor_principal_id=event.actor_principal_id,
                document_id=event.document_id,
                job_id=event.job_id,
                review_id=event.review_id,
                correlation_id=event.correlation_id,
                details_version=1,
                details=event.details,
            )
            for event in history.events
        ],
    )
