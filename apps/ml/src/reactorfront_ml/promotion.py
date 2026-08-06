from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from reactorfront_ml.candidate import load_candidate_build_manifest
from reactorfront_ml.evaluation import (
    EvaluationError,
    canonical_json_bytes,
    load_candidate_comparison,
    load_dataset_snapshot,
    load_evaluation_policy,
    load_evaluation_report,
    sha256_bytes,
)
from reactorfront_ml.model import (
    CLASS_NAMES,
    MODEL_NAME,
    MODEL_SCHEMA_VERSION,
    MODEL_VERSION,
    GeneratedArtifact,
    ModelArtifactError,
    generate_artifact,
)

PROMOTION_SCHEMA_VERSION = "promoted-model-v1"
PROMOTION_SELECTION = "candidate-promotion"
ROLLBACK_SELECTION = "rollback"


class PromotionError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class PromotedModel:
    selection_type: str
    model_name: str
    model_version: str
    artifact: GeneratedArtifact
    evaluation_report: dict[str, Any]
    comparison: dict[str, Any]
    manifest: dict[str, Any]
    manifest_sha256: str


def _canonical_manifest(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PromotionError("PROMOTION_INVALID_JSON") from error
    if not isinstance(value, dict):
        raise PromotionError("PROMOTION_INVALID_JSON_SHAPE")
    try:
        canonical = canonical_json_bytes(value)
    except EvaluationError as error:
        raise PromotionError("PROMOTION_NONCANONICAL_MANIFEST") from error
    if raw != canonical:
        raise PromotionError("PROMOTION_NONCANONICAL_MANIFEST")
    return cast(dict[str, Any], value), raw


def _validate_schema(value: dict[str, Any], schema_path: Path) -> None:
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        errors = sorted(
            Draft202012Validator(schema).iter_errors(value),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, SchemaError) as error:
        raise PromotionError("PROMOTION_INVALID_SCHEMA") from error
    if errors:
        raise PromotionError("PROMOTION_SCHEMA_VIOLATION")


def _repository_path(repository_root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise PromotionError("PROMOTION_INVALID_EVIDENCE_PATH")
    portable = PurePosixPath(value)
    if portable.is_absolute() or ".." in portable.parts or portable.as_posix() != value:
        raise PromotionError("PROMOTION_INVALID_EVIDENCE_PATH")
    root = repository_root.resolve()
    resolved = (root / Path(*portable.parts)).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise PromotionError("PROMOTION_INVALID_EVIDENCE_PATH") from error
    return resolved


def load_promoted_model(
    manifest_path: Path,
    schema_path: Path,
    *,
    repository_root: Path,
) -> PromotedModel:
    manifest, raw = _canonical_manifest(manifest_path)
    _validate_schema(manifest, schema_path)

    if (
        manifest["schemaVersion"] != PROMOTION_SCHEMA_VERSION
        or manifest["taskOntology"] != list(CLASS_NAMES)
        or manifest["artifactSchemaVersion"] != MODEL_SCHEMA_VERSION
    ):
        raise PromotionError("PROMOTION_UNSUPPORTED_BOUNDARY")

    evidence = cast(dict[str, Any], manifest["evidence"])
    paths = {key: _repository_path(repository_root, value) for key, value in evidence.items()}

    try:
        snapshot = load_dataset_snapshot(repository_root, paths["datasetSnapshotPath"])
        policy = load_evaluation_policy(paths["evaluationPolicyPath"])
        candidate_build, _, candidate_artifact = load_candidate_build_manifest(
            paths["candidateBuildPath"],
            snapshot,
            policy,
            paths["dependencyLockPath"],
        )
        champion_artifact = generate_artifact(paths["championTrainingDataPath"])
        champion_report, _ = load_evaluation_report(
            paths["championReportPath"],
            paths["evaluationReportSchemaPath"],
            snapshot,
            policy,
            champion_artifact.sha256,
            evaluation_role="champion-baseline",
            model_name=MODEL_NAME,
            model_version=MODEL_VERSION,
        )
        candidate_report, _ = load_evaluation_report(
            paths["candidateReportPath"],
            paths["evaluationReportSchemaPath"],
            snapshot,
            policy,
            candidate_artifact.sha256,
            evaluation_role="candidate",
            model_name=cast(str, candidate_build["modelName"]),
            model_version=cast(str, candidate_build["modelVersion"]),
        )
        comparison, _ = load_candidate_comparison(
            paths["candidateComparisonPath"],
            paths["candidateComparisonSchemaPath"],
            champion_report,
            candidate_report,
            paths["evaluationReportSchemaPath"],
            snapshot,
            policy,
            champion_artifact.sha256,
            candidate_artifact.sha256,
            candidate_model_name=cast(str, candidate_build["modelName"]),
            candidate_model_version=cast(str, candidate_build["modelVersion"]),
        )
    except (EvaluationError, ModelArtifactError, OSError, ValueError) as error:
        raise PromotionError("PROMOTION_EVIDENCE_INVALID") from error

    selection_type = cast(str, manifest["selectionType"])
    if selection_type == PROMOTION_SELECTION:
        if comparison["eligible"] is not True:
            raise PromotionError("PROMOTION_CANDIDATE_INELIGIBLE")
        selected_identity = cast(dict[str, Any], comparison["candidate"])
        selected_artifact = candidate_artifact
        selected_report = candidate_report
    elif selection_type == ROLLBACK_SELECTION:
        selected_identity = cast(dict[str, Any], comparison["champion"])
        selected_artifact = champion_artifact
        selected_report = champion_report
    else:
        raise PromotionError("PROMOTION_UNSUPPORTED_SELECTION")

    expected_identity = {
        "artifactSha256": selected_artifact.sha256,
        "modelName": manifest["modelName"],
        "modelVersion": manifest["modelVersion"],
        "reportSha256": selected_report["reportSha256"],
    }
    if selected_identity != expected_identity:
        raise PromotionError("PROMOTION_SELECTED_IDENTITY_MISMATCH")

    expected_lineage = {
        "artifactSha256": selected_artifact.sha256,
        "comparisonSha256": comparison["comparisonSha256"],
        "datasetSha256": snapshot.dataset_sha256,
        "datasetVersion": snapshot.dataset_version,
        "evaluationPolicySha256": policy.sha256,
        "evaluationPolicyVersion": policy.version,
        "evaluationReportSha256": selected_report["reportSha256"],
        "modelName": selected_identity["modelName"],
        "modelVersion": selected_identity["modelVersion"],
        "pipelineVersion": policy.value["pipelineVersion"],
        "preprocessingVersion": policy.value["preprocessingVersion"],
    }
    if any(manifest.get(key) != value for key, value in expected_lineage.items()):
        raise PromotionError("PROMOTION_LINEAGE_MISMATCH")

    return PromotedModel(
        selection_type=selection_type,
        model_name=cast(str, selected_identity["modelName"]),
        model_version=cast(str, selected_identity["modelVersion"]),
        artifact=selected_artifact,
        evaluation_report=selected_report,
        comparison=comparison,
        manifest=manifest,
        manifest_sha256=sha256_bytes(raw),
    )
