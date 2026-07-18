from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


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
