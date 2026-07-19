from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

import reactorfront_ml.health as health
import reactorfront_ml.runtime as runtime
from reactorfront_ml.domain import ResultEventPublisher, SourceStorage
from reactorfront_ml.model import ModelArtifactError
from reactorfront_ml.settings import Settings
from tests.fakes import FakePublisher, FakeStorage


def settings(tmp_path: Path) -> Settings:
    return Settings(
        model_artifact_path=tmp_path / "model.json",
        model_checksum_path=tmp_path / "model.sha256",
        event_contract_directory=tmp_path / "contracts",
    )


def test_build_runtime_wires_independent_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: dict[str, object] = {}
    fake_storage = FakeStorage()
    fake_publisher = FakePublisher()
    fake_classifier = SimpleNamespace(checksum="a" * 64)
    fake_validator = SimpleNamespace()

    monkeypatch.setattr(
        runtime.JsonSchemaEventValidator,
        "__new__",
        lambda cls, **values: observed.setdefault("validator", fake_validator),
    )
    monkeypatch.setattr(
        runtime.S3SourceStorage,
        "create",
        lambda **values: observed.setdefault("storage", fake_storage),
    )
    monkeypatch.setattr(
        runtime,
        "DocumentClassifier",
        lambda **values: observed.setdefault("classifier", fake_classifier),
    )
    monkeypatch.setattr(
        runtime,
        "PikaResultEventPublisher",
        lambda **values: observed.setdefault("publisher", fake_publisher),
    )

    built = runtime.build_runtime(settings(tmp_path))

    assert built.storage is fake_storage
    assert built.publisher is fake_publisher
    assert built.classifier is fake_classifier
    assert set(observed) == {"validator", "storage", "classifier", "publisher"}


def test_readiness_requires_model_storage_and_broker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    storage = FakeStorage(ready=True)
    publisher = FakePublisher(ready=True)
    built = SimpleNamespace(
        storage=cast(SourceStorage, storage),
        publisher=cast(ResultEventPublisher, publisher),
    )
    monkeypatch.setattr(health, "build_runtime", lambda _: built)

    assert health.is_ready(settings(tmp_path))
    publisher.ready = False
    assert not health.is_ready(settings(tmp_path))


def test_readiness_fails_closed_on_invalid_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail(_: Settings) -> object:
        raise ModelArtifactError("invalid")

    monkeypatch.setattr(health, "build_runtime", fail)
    assert not health.is_ready(settings(tmp_path))
