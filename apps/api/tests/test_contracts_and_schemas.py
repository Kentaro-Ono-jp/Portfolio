from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from jsonschema import ValidationError

from reactorfront_api.domain import DocumentStatusRecord, ProcessingStatus
from reactorfront_api.event_contracts import JsonSchemaEventValidator
from reactorfront_api.schemas import serialize_document_status

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_DIRECTORY = REPOSITORY_ROOT / "packages" / "contracts" / "events"
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
