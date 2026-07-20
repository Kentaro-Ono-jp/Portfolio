from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from math import isfinite
from pathlib import Path
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource

from reactorfront_api.domain import InvalidResultEvent, ResultEvent, ResultEventType


class JsonSchemaEventValidator:
    def __init__(self, *, contract_directory: Path) -> None:
        resources: dict[str, Resource[object]] = {}
        schemas: dict[str, dict[str, object]] = {}

        for schema_path in sorted(contract_directory.glob("*.schema.json")):
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            if not isinstance(schema, dict) or not isinstance(schema.get("$id"), str):
                raise ValueError(f"Event schema has no string $id: {schema_path}")
            schema_id = schema["$id"]
            schemas[schema_id] = schema
            resources[schema_id] = Resource.from_contents(schema)

        self._schema_base = "https://portfolio.reactorfront.dev/contracts/events"
        self._schemas = schemas
        self._registry = Registry().with_resources(resources.items())
        self._format_checker = FormatChecker()

    def validate(self, *, event_type: str, payload: dict[str, object]) -> None:
        schema_id = f"{self._schema_base}/{event_type}.schema.json"
        try:
            schema = self._schemas[schema_id]
        except KeyError as error:
            raise ValueError(f"No event contract exists for {event_type}") from error

        Draft202012Validator(
            schema,
            registry=self._registry,
            format_checker=self._format_checker,
        ).validate(payload)


def parse_result_event(
    payload: object,
    *,
    validator: JsonSchemaEventValidator,
) -> ResultEvent:
    if not isinstance(payload, dict) or not all(isinstance(key, str) for key in payload):
        raise InvalidResultEvent("Result event must be a string-keyed object")

    typed_payload: dict[str, object] = payload
    try:
        event_type = ResultEventType(str(typed_payload["eventType"]))
        validator.validate(event_type=event_type.value, payload=typed_payload)
        occurred_at = datetime.fromisoformat(str(typed_payload["occurredAt"]))
        if occurred_at.tzinfo is None:
            raise ValueError("Result event timestamp must include a timezone")

        classification: str | None = None
        confidence: float | None = None
        failure_code: str | None = None
        if event_type is ResultEventType.COMPLETED:
            classification = str(typed_payload["classification"])
            confidence_value = typed_payload["confidence"]
            if not isinstance(confidence_value, int | float):
                raise TypeError("Completed confidence must be numeric")
            confidence = float(confidence_value)
            if not isfinite(confidence):
                raise ValueError("Completed confidence must be finite")
        elif event_type is ResultEventType.FAILED:
            failure_code = str(typed_payload["failureCode"])

        logical_payload = {
            key: value for key, value in typed_payload.items() if key != "occurredAt"
        }
        logical_payload_sha256 = sha256(
            json.dumps(
                logical_payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        return ResultEvent(
            event_id=UUID(str(typed_payload["eventId"])),
            event_type=event_type,
            occurred_at=occurred_at.astimezone(UTC),
            correlation_id=UUID(str(typed_payload["correlationId"])),
            document_id=UUID(str(typed_payload["documentId"])),
            job_id=UUID(str(typed_payload["jobId"])),
            object_key=str(typed_payload["objectKey"]),
            source_sha256=str(typed_payload["sourceSha256"]),
            model_version=str(typed_payload["modelVersion"]),
            logical_payload_sha256=logical_payload_sha256,
            classification=classification,
            confidence=confidence,
            failure_code=failure_code,
        )
    except (KeyError, TypeError, ValueError, ValidationError) as error:
        raise InvalidResultEvent("Result event failed canonical validation") from error
