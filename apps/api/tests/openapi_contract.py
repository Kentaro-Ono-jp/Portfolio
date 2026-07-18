from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol, cast

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
OPENAPI_PATH = REPOSITORY_ROOT / "packages" / "contracts" / "openapi" / "openapi.yaml"
OPENAPI_URI = "urn:reactorfront:canonical-openapi"
OPENAPI = cast(dict[str, object], yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8")))
OPENAPI_REGISTRY = Registry().with_resource(
    OPENAPI_URI,
    Resource(contents=OPENAPI, specification=DRAFT202012),
)


class HttpResponse(Protocol):
    @property
    def status_code(self) -> int: ...

    @property
    def headers(self) -> Mapping[str, str]: ...

    def json(self) -> object: ...


def assert_openapi_response(response: HttpResponse, *, path: str, method: str) -> None:
    operation = _mapping(_mapping(OPENAPI["paths"])[path])[method.lower()]
    declared_response = _mapping(_mapping(operation)["responses"])[str(response.status_code)]
    response_contract = _resolve_local_reference(_mapping(declared_response))
    content = _mapping(response_contract["content"])
    actual_media_type = response.headers["content-type"].split(";", maxsplit=1)[0].lower()
    assert actual_media_type in content, (
        f"{method.upper()} {path} returned undeclared media type {actual_media_type}"
    )

    media_contract = _mapping(content[actual_media_type])
    _validate(media_contract["schema"], response.json())

    for header_name, header_contract in _mapping(response_contract.get("headers", {})).items():
        assert header_name in response.headers, (
            f"{method.upper()} {path} {response.status_code} omitted {header_name}"
        )
        resolved_header = _resolve_local_reference(_mapping(header_contract))
        _validate(resolved_header["schema"], response.headers[header_name])


def _validate(schema: object, instance: object) -> None:
    validator = Draft202012Validator(
        _absolute_references(schema),
        registry=OPENAPI_REGISTRY,
        format_checker=FormatChecker(),
    )
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.path))
    assert not errors, "; ".join(error.message for error in errors)


def _resolve_local_reference(value: dict[str, object]) -> dict[str, object]:
    reference = value.get("$ref")
    if not isinstance(reference, str) or not reference.startswith("#/"):
        return value
    current: object = OPENAPI
    for raw_segment in reference[2:].split("/"):
        segment = raw_segment.replace("~1", "/").replace("~0", "~")
        current = _mapping(current)[segment]
    return _resolve_local_reference(_mapping(current))


def _absolute_references(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: OPENAPI_URI + item
            if key == "$ref" and isinstance(item, str) and item.startswith("#/")
            else _absolute_references(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_absolute_references(item) for item in value]
    return value


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)
