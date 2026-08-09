from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.measure_container_resources import (
    load_configuration,
    parse_memory_bytes,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("512B", 512),
        ("1KiB", 1024),
        ("1.5MiB", round(1.5 * 1024**2)),
        ("2GB", 2_000_000_000),
    ],
)
def test_parse_memory_bytes_supports_docker_units(value: str, expected: int) -> None:
    assert parse_memory_bytes(value) == expected


def test_runtime_sizing_configuration_covers_valid_fargate_tasks() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    configuration = load_configuration(repository_root / "infra/aws/runtime-sizing.json")

    assert set(configuration["processes"]) == {
        "web",
        "api",
        "api-outbox",
        "api-events",
        "api-migration",
        "ml-worker",
    }
    assert configuration["tasks"]["web"] == {"cpuUnits": 256, "memoryMiB": 512}


def test_runtime_sizing_configuration_rejects_invalid_task_pair(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[3]
    document = json.loads(
        (repository_root / "infra/aws/runtime-sizing.json").read_text(encoding="utf-8")
    )
    document["tasks"]["web"]["memoryMiB"] = 256
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="valid Fargate"):
        load_configuration(invalid)
