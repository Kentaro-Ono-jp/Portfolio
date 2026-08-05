from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from reactorfront_api.domain import (
    AuditHistory,
    DocumentStatusRecord,
    MeasuredModelEvidence,
    ProcessingStatus,
    ReviewRecord,
    ReviewStatus,
)


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


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


class LegacyModelEvidenceResponse(ApiModel):
    status: Literal["legacy-unmeasured"]


class MeasuredModelEvidenceResponse(ApiModel):
    status: Literal["measured"]
    dataset_version: str = Field(alias="datasetVersion", min_length=1, max_length=128)
    dataset_sha256: str = Field(alias="datasetSha256", pattern=r"^[a-f0-9]{64}$")
    preprocessing_version: str = Field(alias="preprocessingVersion", min_length=1, max_length=128)
    pipeline_version: str = Field(alias="pipelineVersion", min_length=1, max_length=128)
    artifact_sha256: str = Field(alias="artifactSha256", pattern=r"^[a-f0-9]{64}$")
    evaluation_policy_version: str = Field(
        alias="evaluationPolicyVersion", min_length=1, max_length=128
    )
    evaluation_policy_sha256: str = Field(alias="evaluationPolicySha256", pattern=r"^[a-f0-9]{64}$")
    evaluation_report_sha256: str = Field(alias="evaluationReportSha256", pattern=r"^[a-f0-9]{64}$")


ModelEvidenceResponse = Annotated[
    LegacyModelEvidenceResponse | MeasuredModelEvidenceResponse,
    Field(discriminator="status"),
]


class CompletedDocumentStatusResponse(StatusIdentity):
    status: Literal[ProcessingStatus.COMPLETED]
    classification: Literal["invoice", "report"]
    confidence: float = Field(ge=0, le=1)
    model_version: str = Field(alias="modelVersion", min_length=1, max_length=128)
    model_evidence: ModelEvidenceResponse = Field(alias="modelEvidence")
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


class ReviewIdentity(ApiModel):
    document_id: UUID = Field(alias="documentId")
    job_id: UUID = Field(alias="jobId")
    machine_classification: Literal["invoice", "report"] = Field(alias="machineClassification")
    machine_confidence: float = Field(alias="machineConfidence", ge=0, le=1)
    model_version: str = Field(alias="modelVersion", min_length=1, max_length=128)
    model_evidence: ModelEvidenceResponse = Field(alias="modelEvidence")


class UnreviewedReviewResponse(ReviewIdentity):
    status: Literal["unreviewed"]
    review_version: Literal[0] = Field(alias="reviewVersion")


class TerminalReviewIdentity(ReviewIdentity):
    review_version: Literal[1] = Field(alias="reviewVersion")
    final_classification: Literal["invoice", "report"] = Field(alias="finalClassification")
    reviewer_principal_id: UUID = Field(alias="reviewerPrincipalId")
    decided_at: datetime = Field(alias="decidedAt")


class ApprovedReviewResponse(TerminalReviewIdentity):
    status: Literal["approved"]

    @model_validator(mode="after")
    def classification_is_unchanged(self) -> ApprovedReviewResponse:
        if self.machine_classification != self.final_classification:
            raise ValueError("An approved review must preserve the machine classification")
        return self


class CorrectedReviewResponse(TerminalReviewIdentity):
    status: Literal["corrected"]

    @model_validator(mode="after")
    def classification_is_changed(self) -> CorrectedReviewResponse:
        if self.machine_classification == self.final_classification:
            raise ValueError("A corrected review must change the machine classification")
        return self


TerminalReviewResponse = Annotated[
    ApprovedReviewResponse | CorrectedReviewResponse,
    Field(discriminator="status"),
]

ReviewResponse = Annotated[
    UnreviewedReviewResponse | ApprovedReviewResponse | CorrectedReviewResponse,
    Field(discriminator="status"),
]


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
    details_version: Literal[1, 2] = Field(alias="detailsVersion")
    details: dict[str, object]

    @model_validator(mode="after")
    def details_match_version(self) -> AuditEventResponse:
        if self.details_version == 1:
            if self.details:
                raise ValueError("Version 1 audit details must be empty")
            return self
        expected = {
            "modelEvidenceStatus",
            "modelVersion",
            "datasetVersion",
            "datasetSha256",
            "preprocessingVersion",
            "pipelineVersion",
            "artifactSha256",
            "evaluationPolicyVersion",
            "evaluationPolicySha256",
            "evaluationReportSha256",
        }
        if self.action != "processing.completed" or set(self.details) != expected:
            raise ValueError("Version 2 audit details must contain exact measured lineage")
        if self.details.get("modelEvidenceStatus") != "measured":
            raise ValueError("Version 2 audit details must be measured")
        for key in expected - {"modelEvidenceStatus"}:
            value = self.details.get(key)
            if not isinstance(value, str) or not value:
                raise ValueError("Version 2 audit lineage values must be non-empty strings")
        for key in (
            "datasetSha256",
            "artifactSha256",
            "evaluationPolicySha256",
            "evaluationReportSha256",
        ):
            value = self.details[key]
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise ValueError("Version 2 audit lineage digests must be SHA-256")
        return self


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
                model_evidence=_serialize_model_evidence(record.model_evidence),
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
        return UnreviewedReviewResponse(
            document_id=record.document_id,
            job_id=record.job_id,
            status=ReviewStatus.UNREVIEWED,
            machine_classification=machine_classification,
            machine_confidence=float(record.machine_confidence),
            model_version=record.model_version,
            model_evidence=_serialize_model_evidence(record.model_evidence),
            review_version=0,
        )

    if (
        record.review_version != 1
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
    if record.status is ReviewStatus.APPROVED:
        if machine_classification != final_classification:
            raise ValueError("An approved review must preserve the machine classification")
        return ApprovedReviewResponse(
            document_id=record.document_id,
            job_id=record.job_id,
            status="approved",
            machine_classification=machine_classification,
            machine_confidence=float(record.machine_confidence),
            model_version=record.model_version,
            model_evidence=_serialize_model_evidence(record.model_evidence),
            review_version=1,
            final_classification=final_classification,
            reviewer_principal_id=record.reviewer_principal_id,
            decided_at=record.decided_at,
        )
    if machine_classification == final_classification:
        raise ValueError("A corrected review must change the machine classification")
    return CorrectedReviewResponse(
        document_id=record.document_id,
        job_id=record.job_id,
        status="corrected",
        machine_classification=machine_classification,
        machine_confidence=float(record.machine_confidence),
        model_version=record.model_version,
        model_evidence=_serialize_model_evidence(record.model_evidence),
        review_version=1,
        final_classification=final_classification,
        reviewer_principal_id=record.reviewer_principal_id,
        decided_at=record.decided_at,
    )


def serialize_terminal_review(record: ReviewRecord) -> TerminalReviewResponse:
    response = serialize_review(record)
    if isinstance(response, UnreviewedReviewResponse):
        raise ValueError("A committed review must be terminal")
    return response


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
                details_version=event.details_version,
                details=event.details,
            )
            for event in history.events
        ],
    )


def _serialize_model_evidence(
    evidence: MeasuredModelEvidence | None,
) -> ModelEvidenceResponse:
    if evidence is None:
        return LegacyModelEvidenceResponse(status="legacy-unmeasured")
    return MeasuredModelEvidenceResponse(
        status="measured",
        dataset_version=evidence.dataset_version,
        dataset_sha256=evidence.dataset_sha256,
        preprocessing_version=evidence.preprocessing_version,
        pipeline_version=evidence.pipeline_version,
        artifact_sha256=evidence.artifact_sha256,
        evaluation_policy_version=evidence.evaluation_policy_version,
        evaluation_policy_sha256=evidence.evaluation_policy_sha256,
        evaluation_report_sha256=evidence.evaluation_report_sha256,
    )
