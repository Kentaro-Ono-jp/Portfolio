from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from reactorfront_ml.domain import (
    ClassificationResult,
    InvalidRequestedEvent,
    ProcessingFailureCode,
)
from reactorfront_ml.event_contracts import (
    JsonSchemaEventValidator,
    parse_requested_event,
)
from reactorfront_ml.events import ResultEventFactory
from reactorfront_ml.model import MODEL_VERSION

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_DIRECTORY = REPOSITORY_ROOT / "packages" / "contracts" / "events"
EXAMPLE_PATH = (
    REPOSITORY_ROOT
    / "packages"
    / "contracts"
    / "examples"
    / "events"
    / "document.processing.requested.v1.json"
)


def validator() -> JsonSchemaEventValidator:
    return JsonSchemaEventValidator(contract_directory=CONTRACT_DIRECTORY)


def test_parse_requested_event_uses_canonical_contract() -> None:
    payload = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))

    request = parse_requested_event(payload, validator=validator())

    assert request.event_id == UUID(payload["eventId"])
    assert request.correlation_id == UUID(payload["correlationId"])
    assert request.object_key == payload["objectKey"]
    assert request.source_sha256 == payload["sourceSha256"]


@pytest.mark.parametrize("payload", [None, [], {"eventType": "wrong"}])
def test_parse_requested_event_rejects_invalid_payload(payload: object) -> None:
    with pytest.raises(InvalidRequestedEvent):
        parse_requested_event(payload, validator=validator())


def test_result_events_are_schema_valid_and_idempotently_identified() -> None:
    payload = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    request = parse_requested_event(payload, validator=validator())

    now = datetime(2026, 7, 19, 3, 0, tzinfo=UTC)
    first = ResultEventFactory(clock=lambda: now)
    second = ResultEventFactory(clock=lambda: now + timedelta(seconds=1))
    result = ClassificationResult(
        classification="invoice",
        confidence=0.91,
        model_version=MODEL_VERSION,
    )

    event_pairs = (
        (
            "document.processing.started.v1",
            first.started(request=request, model_version=MODEL_VERSION),
            second.started(request=request, model_version=MODEL_VERSION),
        ),
        (
            "document.processing.completed.v1",
            first.completed(request=request, result=result),
            second.completed(request=request, result=result),
        ),
        (
            "document.processing.failed.v1",
            first.failed(
                request=request,
                model_version=MODEL_VERSION,
                failure_code=ProcessingFailureCode.INVALID_PDF,
            ),
            second.failed(
                request=request,
                model_version=MODEL_VERSION,
                failure_code=ProcessingFailureCode.INVALID_PDF,
            ),
        ),
    )

    for event_type, first_event, second_event in event_pairs:
        validator().validate(event_type=event_type, payload=first_event)
        assert first_event["eventId"] == second_event["eventId"]
        assert first_event["occurredAt"] != second_event["occurredAt"]
