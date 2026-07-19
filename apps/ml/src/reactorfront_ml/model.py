from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

import torch

from reactorfront_ml.domain import ClassificationResult

MODEL_NAME = "reactorfront-document-type"
MODEL_VERSION = "document-type-v1"
MODEL_SCHEMA_VERSION = 1
TRAINING_SEED = 20260719
CLASS_NAMES = ("invoice", "report")
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class TrainingExample(TypedDict):
    label: str
    text: str


class TrainingDocument(TypedDict):
    description: str
    examples: list[TrainingExample]


@dataclass(frozen=True, slots=True)
class GeneratedArtifact:
    content: bytes
    sha256: str
    training_accuracy: float


class ModelArtifactError(Exception):
    pass


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return " ".join(TOKEN_PATTERN.findall(normalized))


def tokenize(text: str) -> list[str]:
    normalized = normalize_text(text)
    return normalized.split() if normalized else []


def _load_training_document(path: Path) -> TrainingDocument:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ModelArtifactError("Training data must be an object")
    description = value.get("description")
    examples = value.get("examples")
    if not isinstance(description, str) or not isinstance(examples, list):
        raise ModelArtifactError("Training data has an invalid shape")

    validated: list[TrainingExample] = []
    for item in examples:
        if not isinstance(item, dict):
            raise ModelArtifactError("Training example must be an object")
        label = item.get("label")
        text = item.get("text")
        if label not in CLASS_NAMES or not isinstance(text, str) or not tokenize(text):
            raise ModelArtifactError("Training example is invalid")
        validated.append({"label": cast(str, label), "text": text})
    if not validated or {item["label"] for item in validated} != set(CLASS_NAMES):
        raise ModelArtifactError("Training data must contain both supported classes")
    return {"description": description, "examples": validated}


def _feature_vector(tokens: list[str], vocabulary: list[str]) -> torch.Tensor:
    indexes = {token: index for index, token in enumerate(vocabulary)}
    vector = torch.zeros(len(vocabulary), dtype=torch.float64)
    for token in tokens:
        index = indexes.get(token)
        if index is not None:
            vector[index] += 1.0
    return vector


def _rounded(values: torch.Tensor) -> list[float] | list[list[float]]:
    raw = values.tolist()
    if raw and isinstance(raw[0], list):
        return [[float(f"{item:.8f}") for item in row] for row in raw]
    return [float(f"{item:.8f}") for item in raw]


def _artifact_bytes(value: dict[str, object]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def generate_artifact(training_data_path: Path) -> GeneratedArtifact:
    torch.manual_seed(TRAINING_SEED)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)

    document = _load_training_document(training_data_path)
    examples = document["examples"]
    vocabulary = sorted({token for item in examples for token in tokenize(item["text"])})
    class_indexes = {name: index for index, name in enumerate(CLASS_NAMES)}
    token_counts = torch.ones((len(CLASS_NAMES), len(vocabulary)), dtype=torch.float64)
    class_counts = torch.ones(len(CLASS_NAMES), dtype=torch.float64)

    for item in examples:
        class_index = class_indexes[item["label"]]
        token_counts[class_index] += _feature_vector(tokenize(item["text"]), vocabulary)
        class_counts[class_index] += 1.0

    token_log_probabilities = torch.log(token_counts / token_counts.sum(dim=1, keepdim=True))
    class_log_probabilities = torch.log(class_counts / class_counts.sum())
    weights = torch.tensor(_rounded(token_log_probabilities), dtype=torch.float64)
    bias = torch.tensor(_rounded(class_log_probabilities), dtype=torch.float64)

    correct = 0
    for item in examples:
        features = _feature_vector(tokenize(item["text"]), vocabulary)
        prediction = int(torch.argmax(torch.mv(weights, features) + bias).item())
        correct += CLASS_NAMES[prediction] == item["label"]
    accuracy = correct / len(examples)

    training_bytes = training_data_path.read_bytes()
    artifact: dict[str, object] = {
        "schemaVersion": MODEL_SCHEMA_VERSION,
        "modelName": MODEL_NAME,
        "modelVersion": MODEL_VERSION,
        "classes": list(CLASS_NAMES),
        "vocabulary": vocabulary,
        "weights": weights.tolist(),
        "bias": bias.tolist(),
        "training": {
            "algorithm": "pytorch-multinomial-naive-bayes-linear",
            "seed": TRAINING_SEED,
            "sampleCount": len(examples),
            "dataSha256": hashlib.sha256(training_bytes).hexdigest(),
            "trainingAccuracy": float(f"{accuracy:.8f}"),
        },
    }
    content = _artifact_bytes(artifact)
    return GeneratedArtifact(
        content=content,
        sha256=hashlib.sha256(content).hexdigest(),
        training_accuracy=accuracy,
    )


class DocumentClassifier:
    def __init__(self, *, artifact_path: Path, checksum_path: Path) -> None:
        content = artifact_path.read_bytes()
        expected_checksum = checksum_path.read_text(encoding="utf-8").strip()
        actual_checksum = hashlib.sha256(content).hexdigest()
        if actual_checksum != expected_checksum:
            raise ModelArtifactError("Model artifact checksum does not match")

        value = json.loads(content)
        if not isinstance(value, dict):
            raise ModelArtifactError("Model artifact must be an object")
        if value.get("schemaVersion") != MODEL_SCHEMA_VERSION:
            raise ModelArtifactError("Model artifact schema is unsupported")
        if value.get("modelName") != MODEL_NAME or value.get("modelVersion") != MODEL_VERSION:
            raise ModelArtifactError("Model identity does not match the runtime")
        if value.get("classes") != list(CLASS_NAMES):
            raise ModelArtifactError("Model classes do not match the runtime")

        vocabulary = value.get("vocabulary")
        weights = value.get("weights")
        bias = value.get("bias")
        if not isinstance(vocabulary, list) or not all(
            isinstance(item, str) for item in vocabulary
        ):
            raise ModelArtifactError("Model vocabulary is invalid")
        try:
            weight_tensor = torch.tensor(weights, dtype=torch.float64)
            bias_tensor = torch.tensor(bias, dtype=torch.float64)
        except (TypeError, ValueError) as error:
            raise ModelArtifactError("Model parameters are invalid") from error
        if weight_tensor.shape != (len(CLASS_NAMES), len(vocabulary)):
            raise ModelArtifactError("Model weight dimensions are invalid")
        if bias_tensor.shape != (len(CLASS_NAMES),):
            raise ModelArtifactError("Model bias dimensions are invalid")
        if not torch.isfinite(weight_tensor).all() or not torch.isfinite(bias_tensor).all():
            raise ModelArtifactError("Model parameters must be finite")

        self._vocabulary = cast(list[str], vocabulary)
        self._weights = weight_tensor
        self._bias = bias_tensor
        self.checksum = actual_checksum

    def classify(self, text: str) -> ClassificationResult:
        tokens = tokenize(text)
        if not tokens:
            raise ModelArtifactError("Cannot classify empty normalized text")
        features = _feature_vector(tokens, self._vocabulary)
        logits = torch.mv(self._weights, features) + self._bias
        probabilities = torch.softmax(logits, dim=0)
        winner = int(torch.argmax(probabilities).item())
        confidence = float(probabilities[winner].item())
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ModelArtifactError("Model confidence is invalid")
        return ClassificationResult(
            classification=CLASS_NAMES[winner],
            confidence=confidence,
            model_version=MODEL_VERSION,
        )
