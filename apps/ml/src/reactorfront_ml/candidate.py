from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from reactorfront_ml.evaluation import (
    PIPELINE_VERSION,
    PREPROCESSING_VERSION,
    DatasetSnapshot,
    EvaluationError,
    EvaluationPolicy,
    canonical_json_bytes,
    sha256_bytes,
)
from reactorfront_ml.model import (
    CLASS_NAMES,
    MODEL_NAME,
    MODEL_SCHEMA_VERSION,
    TRAINING_ALGORITHM,
    TRAINING_SEED,
    GeneratedArtifact,
    TrainingDocument,
    generate_artifact_from_document,
)

CANDIDATE_BUILD_SCHEMA_VERSION = "candidate-build-v1"
CANDIDATE_MODEL_VERSION = "document-type-candidate-v1"
DEPENDENCY_LOCK_IDENTITY = "apps/ml/uv.lock"
EXPECTED_TRAINING_SAMPLE_COUNT = 12
CONFIDENCE_TREATMENT = "uncalibrated-model-score"


@dataclass(frozen=True, slots=True)
class CandidateBuild:
    artifact: GeneratedArtifact
    manifest: dict[str, Any]


def _canonical_training_identity(snapshot: DatasetSnapshot) -> tuple[list[dict[str, str]], str]:
    records = [
        {
            "label": sample.label,
            "sampleId": sample.sample_id,
            "sourceSha256": sample.source_sha256,
        }
        for sample in snapshot.samples_for("train")
    ]
    return records, sha256_bytes(canonical_json_bytes(records))


def build_candidate(
    snapshot: DatasetSnapshot,
    policy: EvaluationPolicy,
    dependency_lock_path: Path,
) -> CandidateBuild:
    training_samples = snapshot.samples_for("train")
    if (
        len(training_samples) != EXPECTED_TRAINING_SAMPLE_COUNT
        or {sample.label for sample in training_samples} != set(CLASS_NAMES)
        or any(snapshot.assignments[sample.sample_id] != "train" for sample in training_samples)
    ):
        raise EvaluationError("EVAL_CANDIDATE_TRAINING_MEMBERSHIP_MISMATCH")
    if (
        policy.value["pipelineVersion"] != PIPELINE_VERSION
        or policy.value["preprocessingVersion"] != PREPROCESSING_VERSION
    ):
        raise EvaluationError("EVAL_CANDIDATE_POLICY_MISMATCH")
    try:
        dependency_bytes = dependency_lock_path.read_bytes()
    except OSError as error:
        raise EvaluationError("EVAL_CANDIDATE_DEPENDENCY_IDENTITY_MISSING") from error
    if dependency_lock_path.name != "uv.lock" or not dependency_bytes:
        raise EvaluationError("EVAL_CANDIDATE_DEPENDENCY_IDENTITY_MISSING")

    training_records, training_data_sha256 = _canonical_training_identity(snapshot)
    training_sample_ids = [record["sampleId"] for record in training_records]
    dependency_sha256 = sha256_bytes(dependency_bytes)
    document = cast(
        TrainingDocument,
        {
            "description": "Canonical candidate training split from the accepted dataset snapshot.",
            "examples": [
                {"label": sample.label, "text": sample.text} for sample in training_samples
            ],
        },
    )
    artifact = generate_artifact_from_document(
        document,
        model_name=MODEL_NAME,
        model_version=CANDIDATE_MODEL_VERSION,
        training_data_sha256=training_data_sha256,
        training_metadata={
            "confidenceTreatment": CONFIDENCE_TREATMENT,
            "datasetSha256": snapshot.dataset_sha256,
            "dependencyLockSha256": dependency_sha256,
            "pipelineVersion": PIPELINE_VERSION,
            "preprocessingVersion": PREPROCESSING_VERSION,
            "splitSha256": snapshot.split_sha256,
            "trainingSampleIds": training_sample_ids,
        },
    )
    manifest: dict[str, Any] = {
        "artifactSchemaVersion": MODEL_SCHEMA_VERSION,
        "artifactSha256": artifact.sha256,
        "classes": list(CLASS_NAMES),
        "confidenceTreatment": {
            "calibrationClaim": False,
            "method": "none",
            "validationSampleIds": [],
        },
        "corpusSha256": snapshot.corpus_sha256,
        "datasetSha256": snapshot.dataset_sha256,
        "datasetVersion": snapshot.dataset_version,
        "dependency": {
            "lockPath": DEPENDENCY_LOCK_IDENTITY,
            "sha256": dependency_sha256,
        },
        "modelName": MODEL_NAME,
        "modelVersion": CANDIDATE_MODEL_VERSION,
        "pipelineVersion": PIPELINE_VERSION,
        "policySha256": policy.sha256,
        "policyVersion": policy.version,
        "preprocessingVersion": PREPROCESSING_VERSION,
        "schemaVersion": CANDIDATE_BUILD_SCHEMA_VERSION,
        "splitSha256": snapshot.split_sha256,
        "training": {
            "algorithm": TRAINING_ALGORITHM,
            "dataSha256": training_data_sha256,
            "sampleCount": len(training_samples),
            "sampleIds": training_sample_ids,
            "seed": TRAINING_SEED,
            "trainingAccuracy": float(f"{artifact.training_accuracy:.8f}"),
        },
    }
    return CandidateBuild(artifact=artifact, manifest=manifest)


def load_candidate_build_manifest(
    path: Path,
    snapshot: DatasetSnapshot,
    policy: EvaluationPolicy,
    dependency_lock_path: Path,
) -> tuple[dict[str, Any], bytes, GeneratedArtifact]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvaluationError("EVAL_INVALID_CANDIDATE_BUILD_MANIFEST") from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise EvaluationError("EVAL_INVALID_CANDIDATE_BUILD_MANIFEST")
    expected = build_candidate(snapshot, policy, dependency_lock_path)
    if value != expected.manifest:
        raise EvaluationError("EVAL_CANDIDATE_BUILD_MANIFEST_MISMATCH")
    return cast(dict[str, Any], value), raw, expected.artifact
