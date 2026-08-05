from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
import yaml
from jsonschema import ValidationError
from pydantic import ValidationError as PydanticValidationError

from reactorfront_api.domain import (
    DocumentStatusRecord,
    MeasuredModelEvidence,
    ProcessingStatus,
    ReviewRecord,
    ReviewStatus,
    review_entity_tag,
)
from reactorfront_api.event_contracts import JsonSchemaEventValidator
from reactorfront_api.schemas import AuditEventResponse, serialize_document_status, serialize_review

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_DIRECTORY = REPOSITORY_ROOT / "packages" / "contracts" / "events"
OPENAPI_PATH = REPOSITORY_ROOT / "packages" / "contracts" / "openapi" / "openapi.yaml"
DOCUMENT_ID = UUID("22222222-2222-4222-8222-222222222222")
JOB_ID = UUID("33333333-3333-4333-8333-333333333333")
NOW = datetime(2026, 7, 18, 9, 0, tzinfo=UTC)


def requested_event() -> dict[str, object]:
    return {
        "eventId": "44444444-4444-4444-8444-444444444444",
        "eventType": "document.processing.requested.v1",
        "occurredAt": "2026-07-18T09:00:00Z",
        "correlationId": "11111111-1111-4111-8111-111111111111",
        "documentId": str(DOCUMENT_ID),
        "jobId": str(JOB_ID),
        "objectKey": f"documents/{DOCUMENT_ID}/source.pdf",
        "sourceSha256": "a" * 64,
    }


def test_document_contract_requires_bearer_authentication_and_source_ownership() -> None:
    contract = cast(
        dict[str, object],
        yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8")),
    )
    assert contract["security"] == [{"bearerAuth": []}]
    paths = cast(dict[str, dict[str, dict[str, object]]], contract["paths"])
    protected_operations = [
        paths["/api/v1/documents"]["post"],
        paths["/api/v1/documents/{documentId}"]["get"],
        paths["/api/v1/documents/{documentId}/source"]["get"],
        paths["/api/v1/documents/{documentId}/review"]["get"],
        paths["/api/v1/documents/{documentId}/review"]["put"],
        paths["/api/v1/documents/{documentId}/audit-events"]["get"],
    ]
    assert all("security" not in operation for operation in protected_operations)
    assert paths["/health"]["get"]["security"] == []
    assert paths["/ready"]["get"]["security"] == []
    assert all(
        {"401", "403"} <= cast(dict[str, object], operation["responses"]).keys()
        for operation in protected_operations
    )
    components = cast(dict[str, dict[str, object]], contract["components"])
    assert components["securitySchemes"]["bearerAuth"] == {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": (
            "OAuth access token validated independently by the API. Document "
            "operations require a capability and matching resource ownership."
        ),
    }
    assert {
        "AuthenticationRequired",
        "InsufficientCapability",
        "SourceAccessUnavailable",
        "ReviewNotAvailable",
        "ReviewWriteConflict",
        "PreconditionFailed",
        "PreconditionRequired",
    } <= components["responses"].keys()

    review_put = paths["/api/v1/documents/{documentId}/review"]["put"]
    parameters = [
        cast(dict[str, str], parameter)["$ref"]
        for parameter in cast(list[object], review_put["parameters"])
    ]
    assert parameters[-2:] == [
        "#/components/parameters/IfMatch",
        "#/components/parameters/IdempotencyKey",
    ]


def test_event_validator_uses_repository_contracts() -> None:
    validator = JsonSchemaEventValidator(contract_directory=CONTRACT_DIRECTORY)
    validator.validate(
        event_type="document.processing.requested.v1",
        payload=requested_event(),
    )

    invalid = requested_event()
    invalid["rawException"] = "must never cross the boundary"
    with pytest.raises(ValidationError):
        validator.validate(
            event_type="document.processing.requested.v1",
            payload=invalid,
        )

    with pytest.raises(ValueError, match="No event contract"):
        validator.validate(event_type="unknown.v1", payload={})


def test_event_validator_rejects_schema_without_identifier(tmp_path: Path) -> None:
    (tmp_path / "broken.schema.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match=r"no string \$id"):
        JsonSchemaEventValidator(contract_directory=tmp_path)


@pytest.mark.parametrize(
    "record",
    [
        DocumentStatusRecord(
            document_id=DOCUMENT_ID,
            job_id=JOB_ID,
            status=ProcessingStatus.PROCESSING,
            created_at=NOW,
        ),
        DocumentStatusRecord(
            document_id=DOCUMENT_ID,
            job_id=JOB_ID,
            status=ProcessingStatus.COMPLETED,
            created_at=NOW,
            started_at=NOW,
            completed_at=NOW,
            predicted_class="unknown",
            confidence=0.9,
            model_version="v1",
        ),
        DocumentStatusRecord(
            document_id=DOCUMENT_ID,
            job_id=JOB_ID,
            status=ProcessingStatus.FAILED,
            created_at=NOW,
        ),
    ],
)
def test_serializer_refuses_impossible_persistence_shapes(record: DocumentStatusRecord) -> None:
    with pytest.raises(ValueError):
        serialize_document_status(record)


def test_serializer_supports_queued_and_processing_states() -> None:
    queued = serialize_document_status(
        DocumentStatusRecord(
            document_id=DOCUMENT_ID,
            job_id=JOB_ID,
            status=ProcessingStatus.QUEUED,
            created_at=NOW,
        )
    )
    processing = serialize_document_status(
        DocumentStatusRecord(
            document_id=DOCUMENT_ID,
            job_id=JOB_ID,
            status=ProcessingStatus.PROCESSING,
            created_at=NOW,
            started_at=NOW,
        )
    )
    assert queued.model_dump(by_alias=True, mode="json")["status"] == "queued"
    assert processing.model_dump(by_alias=True, mode="json")["startedAt"] == (
        "2026-07-18T09:00:00Z"
    )


def test_review_serializer_and_entity_tag_preserve_machine_evidence() -> None:
    unreviewed = ReviewRecord(
        document_id=DOCUMENT_ID,
        job_id=JOB_ID,
        status=ReviewStatus.UNREVIEWED,
        machine_classification="invoice",
        machine_confidence=Decimal("0.9876"),
        model_version="document-type-v1",
        review_version=0,
    )
    serialized = serialize_review(unreviewed).model_dump(
        by_alias=True,
        mode="json",
        exclude_none=True,
    )
    assert serialized == {
        "documentId": str(DOCUMENT_ID),
        "jobId": str(JOB_ID),
        "status": "unreviewed",
        "machineClassification": "invoice",
        "machineConfidence": 0.9876,
        "modelVersion": "document-type-v1",
        "modelEvidence": {"status": "legacy-unmeasured"},
        "reviewVersion": 0,
    }
    first_tag = review_entity_tag(unreviewed)
    assert first_tag == review_entity_tag(unreviewed)
    assert first_tag.startswith('"') and first_tag.endswith('"')

    terminal = ReviewRecord(
        document_id=DOCUMENT_ID,
        job_id=JOB_ID,
        status=ReviewStatus.CORRECTED,
        machine_classification="invoice",
        machine_confidence=Decimal("0.9876"),
        model_version="document-type-v1",
        review_version=1,
        review_id=UUID("44444444-4444-4444-8444-444444444444"),
        final_classification="report",
        reviewer_principal_id=UUID("55555555-5555-4555-8555-555555555555"),
        decided_at=NOW,
    )
    assert serialize_review(terminal).status == "corrected"
    assert review_entity_tag(terminal) != first_tag

    approved = ReviewRecord(
        document_id=DOCUMENT_ID,
        job_id=JOB_ID,
        status=ReviewStatus.APPROVED,
        machine_classification="report",
        machine_confidence=Decimal("0.9876"),
        model_version="document-type-v1",
        review_version=1,
        review_id=UUID("66666666-6666-4666-8666-666666666666"),
        final_classification="report",
        reviewer_principal_id=UUID("55555555-5555-4555-8555-555555555555"),
        decided_at=NOW,
    )
    assert serialize_review(approved).status == "approved"


def test_review_entity_tag_binds_every_measured_lineage_identity() -> None:
    evidence = MeasuredModelEvidence(
        dataset_version="dataset-v1",
        dataset_sha256="d" * 64,
        preprocessing_version="preprocessing-v1",
        pipeline_version="pipeline-v1",
        artifact_sha256="a" * 64,
        evaluation_policy_version="policy-v1",
        evaluation_policy_sha256="b" * 64,
        evaluation_report_sha256="c" * 64,
    )
    record = ReviewRecord(
        document_id=DOCUMENT_ID,
        job_id=JOB_ID,
        status=ReviewStatus.UNREVIEWED,
        machine_classification="invoice",
        machine_confidence=Decimal("0.9876"),
        model_version="document-type-v1",
        review_version=0,
        model_evidence=evidence,
    )
    baseline = review_entity_tag(record)
    serialized = serialize_review(record).model_dump(by_alias=True, mode="json")
    assert serialized["modelEvidence"] == {
        "status": "measured",
        "datasetVersion": "dataset-v1",
        "datasetSha256": "d" * 64,
        "preprocessingVersion": "preprocessing-v1",
        "pipelineVersion": "pipeline-v1",
        "artifactSha256": "a" * 64,
        "evaluationPolicyVersion": "policy-v1",
        "evaluationPolicySha256": "b" * 64,
        "evaluationReportSha256": "c" * 64,
    }
    assert review_entity_tag(replace(record, model_evidence=None)) != baseline

    for field_name in evidence.__dataclass_fields__:
        current = getattr(evidence, field_name)
        changed = "f" * 64 if field_name.endswith("sha256") else f"{current}-changed"
        mutated = replace(evidence, **{field_name: changed})
        assert review_entity_tag(replace(record, model_evidence=mutated)) != baseline

    delimiter_left = replace(
        evidence,
        preprocessing_version="alpha\x1fbeta",
        pipeline_version="gamma",
    )
    delimiter_right = replace(
        evidence,
        preprocessing_version="alpha",
        pipeline_version="beta\x1fgamma",
    )
    assert delimiter_left != delimiter_right
    assert review_entity_tag(replace(record, model_evidence=delimiter_left)) != review_entity_tag(
        replace(record, model_evidence=delimiter_right)
    )


def measured_audit_details() -> dict[str, object]:
    return {
        "modelEvidenceStatus": "measured",
        "modelVersion": "document-type-v1",
        "datasetVersion": "dataset-v1",
        "datasetSha256": "d" * 64,
        "preprocessingVersion": "preprocessing-v1",
        "pipelineVersion": "pipeline-v1",
        "artifactSha256": "a" * 64,
        "evaluationPolicyVersion": "policy-v1",
        "evaluationPolicySha256": "b" * 64,
        "evaluationReportSha256": "c" * 64,
    }


def audit_event(
    *, action: str, details_version: int, details: dict[str, object]
) -> dict[str, object]:
    return {
        "eventId": "44444444-4444-4444-8444-444444444444",
        "action": action,
        "occurredAt": NOW,
        "actorPrincipalId": "55555555-5555-4555-8555-555555555555",
        "documentId": DOCUMENT_ID,
        "jobId": JOB_ID,
        "correlationId": "11111111-1111-4111-8111-111111111111",
        "detailsVersion": details_version,
        "details": details,
    }


def test_audit_response_accepts_exact_versioned_details() -> None:
    legacy = AuditEventResponse.model_validate(
        audit_event(action="document.submitted", details_version=1, details={})
    )
    measured = AuditEventResponse.model_validate(
        audit_event(
            action="processing.completed",
            details_version=2,
            details=measured_audit_details(),
        )
    )

    assert legacy.details_version == 1
    assert measured.details_version == 2


@pytest.mark.parametrize(
    ("action", "details_version", "details"),
    [
        ("document.submitted", 1, measured_audit_details()),
        ("processing.completed", 2, {}),
        ("review.approved", 2, measured_audit_details()),
        (
            "processing.completed",
            2,
            {**measured_audit_details(), "unknown": "not-allowed"},
        ),
    ],
)
def test_audit_response_rejects_mismatched_or_noncanonical_details(
    action: str,
    details_version: int,
    details: dict[str, object],
) -> None:
    with pytest.raises(PydanticValidationError):
        AuditEventResponse.model_validate(
            audit_event(action=action, details_version=details_version, details=details)
        )


@pytest.mark.parametrize(
    "record",
    [
        ReviewRecord(
            document_id=DOCUMENT_ID,
            job_id=JOB_ID,
            status=ReviewStatus.UNREVIEWED,
            machine_classification="memo",
            machine_confidence=Decimal("0.5"),
            model_version="v1",
            review_version=0,
        ),
        ReviewRecord(
            document_id=DOCUMENT_ID,
            job_id=JOB_ID,
            status=ReviewStatus.APPROVED,
            machine_classification="invoice",
            machine_confidence=Decimal("0.5"),
            model_version="v1",
            review_version=0,
        ),
        ReviewRecord(
            document_id=DOCUMENT_ID,
            job_id=JOB_ID,
            status=ReviewStatus.APPROVED,
            machine_classification="invoice",
            machine_confidence=Decimal("0.5"),
            model_version="v1",
            review_version=1,
            review_id=UUID("44444444-4444-4444-8444-444444444444"),
            final_classification="report",
            reviewer_principal_id=UUID("55555555-5555-4555-8555-555555555555"),
            decided_at=NOW,
        ),
        ReviewRecord(
            document_id=DOCUMENT_ID,
            job_id=JOB_ID,
            status=ReviewStatus.CORRECTED,
            machine_classification="invoice",
            machine_confidence=Decimal("0.5"),
            model_version="v1",
            review_version=1,
            review_id=UUID("44444444-4444-4444-8444-444444444444"),
            final_classification="invoice",
            reviewer_principal_id=UUID("55555555-5555-4555-8555-555555555555"),
            decided_at=NOW,
        ),
    ],
)
def test_review_serializer_refuses_impossible_shapes(record: ReviewRecord) -> None:
    with pytest.raises(ValueError):
        serialize_review(record)
