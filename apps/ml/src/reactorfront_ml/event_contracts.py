from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource

from reactorfront_ml.domain import InvalidRequestedEvent, ProcessingRequest

REQUESTED_EVENT_TYPE = "document.processing.requested.v1"


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


def parse_requested_event(
    payload: object,
    *,
    validator: JsonSchemaEventValidator,
) -> ProcessingRequest:
    if not isinstance(payload, dict) or not all(isinstance(key, str) for key in payload):
        raise InvalidRequestedEvent("Requested event must be a string-keyed object")
    typed_payload: dict[str, object] = payload
    try:
        validator.validate(event_type=REQUESTED_EVENT_TYPE, payload=typed_payload)
        return ProcessingRequest(
            event_id=UUID(str(typed_payload["eventId"])),
            occurred_at=datetime.fromisoformat(str(typed_payload["occurredAt"])),
            correlation_id=UUID(str(typed_payload["correlationId"])),
            document_id=UUID(str(typed_payload["documentId"])),
            job_id=UUID(str(typed_payload["jobId"])),
            object_key=str(typed_payload["objectKey"]),
            source_sha256=str(typed_payload["sourceSha256"]),
        )
    except (KeyError, ValueError, ValidationError) as error:
        raise InvalidRequestedEvent("Requested event failed canonical validation") from error
