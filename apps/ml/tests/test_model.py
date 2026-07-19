from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from reactorfront_ml.model import (
    CLASS_NAMES,
    MODEL_NAME,
    MODEL_VERSION,
    DocumentClassifier,
    ModelArtifactError,
    generate_artifact,
    normalize_text,
)

TRAINING_DATA = Path(__file__).resolve().parents[1] / "data" / "training.json"


def write_artifact(tmp_path: Path) -> tuple[Path, Path, str]:
    generated = generate_artifact(TRAINING_DATA)
    artifact_path = tmp_path / "model.json"
    checksum_path = tmp_path / "model.sha256"
    artifact_path.write_bytes(generated.content)
    checksum_path.write_text(f"{generated.sha256}\n", encoding="utf-8")
    return artifact_path, checksum_path, generated.sha256


def test_normalize_text_is_deterministic() -> None:
    fullwidth_invoice = "\uff29\uff2e\uff36\uff2f\uff29\uff23\uff25"
    assert normalize_text(f"  {fullwidth_invoice}\nTotal: 42.00! ") == "invoice total 42 00"


def test_generation_is_reproducible_and_records_metadata() -> None:
    first = generate_artifact(TRAINING_DATA)
    second = generate_artifact(TRAINING_DATA)

    assert first.content == second.content
    assert first.sha256 == second.sha256
    assert first.training_accuracy == 1.0
    body = json.loads(first.content)
    assert body["modelName"] == MODEL_NAME
    assert body["modelVersion"] == MODEL_VERSION
    assert body["classes"] == list(CLASS_NAMES)
    assert body["training"]["sampleCount"] == 12


def test_real_pytorch_inference_classifies_invoice_above_threshold(
    tmp_path: Path,
) -> None:
    artifact_path, checksum_path, checksum = write_artifact(tmp_path)
    classifier = DocumentClassifier(
        artifact_path=artifact_path,
        checksum_path=checksum_path,
    )

    result = classifier.classify(
        "INVOICE INV-9001\nBill to ReactorFront\nSubtotal 1200 Tax 120 Total 1320 Amount Due"
    )

    assert result.classification == "invoice"
    assert result.confidence >= 0.70
    assert result.model_version == MODEL_VERSION
    assert classifier.checksum == checksum


def test_real_pytorch_inference_classifies_report(tmp_path: Path) -> None:
    artifact_path, checksum_path, _ = write_artifact(tmp_path)
    classifier = DocumentClassifier(
        artifact_path=artifact_path,
        checksum_path=checksum_path,
    )

    result = classifier.classify(
        "Quarterly operations report with findings analysis risks and recommendations"
    )

    assert result.classification == "report"
    assert result.confidence >= 0.70


def test_classifier_rejects_checksum_mismatch(tmp_path: Path) -> None:
    artifact_path, checksum_path, _ = write_artifact(tmp_path)
    checksum_path.write_text(f"{'0' * 64}\n", encoding="utf-8")

    with pytest.raises(ModelArtifactError, match="checksum"):
        DocumentClassifier(artifact_path=artifact_path, checksum_path=checksum_path)


def test_classifier_rejects_empty_text(tmp_path: Path) -> None:
    artifact_path, checksum_path, _ = write_artifact(tmp_path)
    classifier = DocumentClassifier(
        artifact_path=artifact_path,
        checksum_path=checksum_path,
    )

    with pytest.raises(ModelArtifactError, match="empty"):
        classifier.classify(" \n\t")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: [],
        lambda value: {**value, "schemaVersion": 0},
        lambda value: {**value, "modelName": "other"},
        lambda value: {**value, "classes": ["other"]},
        lambda value: {**value, "vocabulary": [1]},
        lambda value: {**value, "weights": None},
        lambda value: {**value, "weights": [[1.0]]},
        lambda value: {**value, "bias": [0.0]},
    ],
)
def test_classifier_rejects_invalid_artifact_shapes(
    tmp_path: Path,
    mutate: Callable[[dict[str, object]], object],
) -> None:
    generated = generate_artifact(TRAINING_DATA)
    original = json.loads(generated.content)
    value = mutate(original)
    content = (json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n").encode()
    artifact_path = tmp_path / "invalid.json"
    checksum_path = tmp_path / "invalid.sha256"
    artifact_path.write_bytes(content)
    checksum_path.write_text(hashlib.sha256(content).hexdigest(), encoding="utf-8")

    with pytest.raises(ModelArtifactError):
        DocumentClassifier(artifact_path=artifact_path, checksum_path=checksum_path)


@pytest.mark.parametrize(
    "value",
    [
        [],
        {},
        {"description": "invalid", "examples": ["not-an-object"]},
        {"description": "invalid", "examples": [{"label": "other", "text": "text"}]},
        {
            "description": "one class",
            "examples": [{"label": "invoice", "text": "invoice total"}],
        },
    ],
)
def test_generation_rejects_invalid_training_data(tmp_path: Path, value: object) -> None:
    path = tmp_path / "training.json"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ModelArtifactError):
        generate_artifact(path)
