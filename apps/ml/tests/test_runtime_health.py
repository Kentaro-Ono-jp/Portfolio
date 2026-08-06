from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

import reactorfront_ml.health as health
import reactorfront_ml.runtime as runtime
from reactorfront_ml.domain import ResultEventPublisher, SourceStorage
from reactorfront_ml.lineage import RuntimeLineageError, RuntimeModelEvidence
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
    fake_promotion = SimpleNamespace(
        model_name="reactorfront-document-type",
        model_version="document-type-candidate-v1",
    )
    fake_classifier = SimpleNamespace(
        checksum="a" * 64,
        model_version="document-type-candidate-v1",
    )
    fake_validator = SimpleNamespace()
    fake_evidence = RuntimeModelEvidence(
        dataset_version="dataset-v1",
        dataset_sha256="d" * 64,
        preprocessing_version="preprocessing-v1",
        pipeline_version="pipeline-v1",
        artifact_sha256="a" * 64,
        evaluation_policy_version="policy-v1",
        evaluation_policy_sha256="b" * 64,
        evaluation_report_sha256="c" * 64,
    )

    monkeypatch.setattr(
        runtime,
        "JsonSchemaEventValidator",
        lambda **values: observed.setdefault("validator", fake_validator),
    )
    monkeypatch.setattr(
        runtime.S3SourceStorage,
        "create",
        lambda **values: observed.setdefault("storage", fake_storage),
    )
    monkeypatch.setattr(
        runtime,
        "load_promoted_model",
        lambda *args, **values: observed.setdefault("promotion", fake_promotion),
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
    monkeypatch.setattr(
        runtime,
        "load_runtime_model_evidence",
        lambda *args, **values: observed.setdefault("model_evidence", fake_evidence),
    )

    built = runtime.build_runtime(settings(tmp_path))

    assert built.storage is fake_storage
    assert built.publisher is fake_publisher
    assert built.classifier is fake_classifier
    assert set(observed) == {
        "validator",
        "storage",
        "classifier",
        "publisher",
        "promotion",
        "model_evidence",
    }


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


def test_readiness_fails_closed_on_invalid_runtime_lineage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail(_: Settings) -> object:
        raise RuntimeLineageError("invalid")

    monkeypatch.setattr(health, "build_runtime", fail)
    assert not health.is_ready(settings(tmp_path))
