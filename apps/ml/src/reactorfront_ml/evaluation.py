from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

from jsonschema import Draft202012Validator

from reactorfront_ml.model import (
    CLASS_NAMES,
    MODEL_NAME,
    MODEL_VERSION,
    DocumentClassifier,
    ModelArtifactError,
    normalize_text,
)

CORPUS_SCHEMA_VERSION = 1
SPLIT_SCHEMA_VERSION = 1
SNAPSHOT_SCHEMA_VERSION = 1
POLICY_SCHEMA_VERSION = 1
REPORT_SCHEMA_VERSION = "evaluation-report-v1"
COMPARISON_SCHEMA_VERSION = "candidate-comparison-v1"
DATASET_VERSION = "reactorfront-synthetic-documents-v1"
SPLIT_VERSION = "family-disjoint-v1"
POLICY_VERSION = "document-classification-evaluation-v1"
PREPROCESSING_VERSION = "nfkc-ascii-alphanumeric-bow-v1"
PIPELINE_VERSION = "pytorch-multinomial-naive-bayes-linear-v1"
SUPPORTED_PROVENANCE = "repository-owned-synthetic"
SUPPORTED_LICENSE = "MIT"
SUPPORTED_SPLITS = ("train", "validation", "test")
SOURCE_PREFIX = "apps/ml/evaluation/corpus/v1/sources/"
EVALUATION_PREFIX = "apps/ml/evaluation/"


class EvaluationError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class CorpusSample:
    sample_id: str
    label: str
    family_id: str
    source_path: Path
    source_sha256: str
    text: str
    normalized_identity: str


@dataclass(frozen=True, slots=True)
class DatasetSnapshot:
    dataset_version: str
    corpus_sha256: str
    split_sha256: str
    dataset_sha256: str
    samples: tuple[CorpusSample, ...]
    assignments: dict[str, str]

    def samples_for(self, split: str) -> tuple[CorpusSample, ...]:
        return tuple(
            sample for sample in self.samples if self.assignments[sample.sample_id] == split
        )


@dataclass(frozen=True, slots=True)
class EvaluationPolicy:
    value: dict[str, Any]
    sha256: str

    @property
    def version(self) -> str:
        return cast(str, self.value["policyVersion"])


def canonical_json_bytes(value: object) -> bytes:
    try:
        rendered = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise EvaluationError("EVAL_NONCANONICAL_VALUE") from error
    return f"{rendered}\n".encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_object(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvaluationError("EVAL_INVALID_JSON") from error
    if not isinstance(value, dict):
        raise EvaluationError("EVAL_INVALID_JSON_SHAPE")
    if raw != canonical_json_bytes(value):
        raise EvaluationError("EVAL_NONCANONICAL_JSON")
    return cast(dict[str, Any], value), raw


def _portable_path(repository_root: Path, raw: object, prefix: str) -> Path:
    if not isinstance(raw, str) or not raw.startswith(prefix) or "\\" in raw:
        raise EvaluationError("EVAL_UNSAFE_SOURCE_PATH")
    portable = PurePosixPath(raw)
    if portable.is_absolute() or ".." in portable.parts or portable.as_posix() != raw:
        raise EvaluationError("EVAL_UNSAFE_SOURCE_PATH")
    root = repository_root.resolve()
    resolved = (root / Path(*portable.parts)).resolve()
    if not resolved.is_relative_to(root):
        raise EvaluationError("EVAL_UNSAFE_SOURCE_PATH")
    return resolved


def _exact_keys(value: dict[str, Any], expected: set[str], code: str) -> None:
    if set(value) != expected:
        raise EvaluationError(code)


def _required_string(value: object, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise EvaluationError(code)
    return value


def _load_corpus(repository_root: Path, path: Path) -> tuple[tuple[CorpusSample, ...], str]:
    value, raw = _canonical_object(path)
    _exact_keys(
        value,
        {"description", "provenanceClasses", "samples", "schemaVersion"},
        "EVAL_INVALID_CORPUS",
    )
    if (
        value["schemaVersion"] != CORPUS_SCHEMA_VERSION
        or value["provenanceClasses"] != [SUPPORTED_PROVENANCE]
        or not isinstance(value["description"], str)
        or not isinstance(value["samples"], list)
    ):
        raise EvaluationError("EVAL_INVALID_CORPUS")

    samples: list[CorpusSample] = []
    sample_ids: set[str] = set()
    source_digests: set[str] = set()
    for item in value["samples"]:
        if not isinstance(item, dict):
            raise EvaluationError("EVAL_INVALID_SAMPLE")
        _exact_keys(
            item,
            {"familyId", "label", "license", "path", "provenance", "sampleId", "sourceSha256"},
            "EVAL_INVALID_SAMPLE",
        )
        sample_id = _required_string(item["sampleId"], "EVAL_INVALID_SAMPLE")
        if sample_id in sample_ids:
            raise EvaluationError("EVAL_DUPLICATE_SAMPLE_ID")
        sample_ids.add(sample_id)
        label = _required_string(item["label"], "EVAL_INVALID_LABEL")
        if label not in CLASS_NAMES:
            raise EvaluationError("EVAL_INVALID_LABEL")
        if item["provenance"] != SUPPORTED_PROVENANCE or item["license"] != SUPPORTED_LICENSE:
            raise EvaluationError("EVAL_INVALID_PROVENANCE")
        family_id = _required_string(item["familyId"], "EVAL_INVALID_FAMILY")
        source_sha256 = _required_string(item["sourceSha256"], "EVAL_INVALID_SOURCE_DIGEST")
        if len(source_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in source_sha256
        ):
            raise EvaluationError("EVAL_INVALID_SOURCE_DIGEST")
        if source_sha256 in source_digests:
            raise EvaluationError("EVAL_DUPLICATE_SOURCE_DIGEST")
        source_digests.add(source_sha256)
        source_path = _portable_path(repository_root, item["path"], SOURCE_PREFIX)
        try:
            source_bytes = source_path.read_bytes()
            text = source_bytes.decode("utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise EvaluationError("EVAL_MISSING_OR_INVALID_SOURCE") from error
        if sha256_bytes(source_bytes) != source_sha256:
            raise EvaluationError("EVAL_SOURCE_DIGEST_MISMATCH")
        if not text.endswith("\n") or text != f"{text.strip()}\n" or not normalize_text(text):
            raise EvaluationError("EVAL_NONCANONICAL_SOURCE")
        normalized_identity = sha256_bytes(normalize_text(text).encode())
        samples.append(
            CorpusSample(
                sample_id=sample_id,
                label=label,
                family_id=family_id,
                source_path=source_path,
                source_sha256=source_sha256,
                text=text.rstrip("\n"),
                normalized_identity=normalized_identity,
            )
        )
    if not samples or [sample.sample_id for sample in samples] != sorted(sample_ids):
        raise EvaluationError("EVAL_NONCANONICAL_SAMPLE_ORDER")
    return tuple(samples), sha256_bytes(raw)


def _load_split(path: Path, sample_ids: set[str]) -> tuple[dict[str, str], str]:
    value, raw = _canonical_object(path)
    _exact_keys(
        value, {"assignments", "description", "schemaVersion", "splitVersion"}, "EVAL_INVALID_SPLIT"
    )
    if (
        value["schemaVersion"] != SPLIT_SCHEMA_VERSION
        or not isinstance(value["description"], str)
        or value["splitVersion"] != SPLIT_VERSION
        or not isinstance(value["assignments"], list)
    ):
        raise EvaluationError("EVAL_INVALID_SPLIT")
    assignments: dict[str, str] = {}
    ordered_ids: list[str] = []
    for item in value["assignments"]:
        if not isinstance(item, dict) or set(item) != {"sampleId", "split"}:
            raise EvaluationError("EVAL_INVALID_ASSIGNMENT")
        sample_id = _required_string(item["sampleId"], "EVAL_INVALID_ASSIGNMENT")
        split = _required_string(item["split"], "EVAL_INVALID_ASSIGNMENT")
        if sample_id in assignments:
            raise EvaluationError("EVAL_DUPLICATE_ASSIGNMENT")
        if split not in SUPPORTED_SPLITS:
            raise EvaluationError("EVAL_INVALID_ASSIGNMENT")
        assignments[sample_id] = split
        ordered_ids.append(sample_id)
    if set(assignments) != sample_ids:
        raise EvaluationError("EVAL_INCOMPLETE_ASSIGNMENTS")
    if ordered_ids != sorted(ordered_ids):
        raise EvaluationError("EVAL_NONCANONICAL_ASSIGNMENT_ORDER")
    return assignments, sha256_bytes(raw)


def _validate_leakage(samples: tuple[CorpusSample, ...], assignments: dict[str, str]) -> None:
    normalized: dict[str, tuple[str, str]] = {}
    families: dict[str, str] = {}
    labels_by_split: dict[str, set[str]] = {split: set() for split in SUPPORTED_SPLITS}
    for sample in samples:
        split = assignments[sample.sample_id]
        labels_by_split[split].add(sample.label)
        prior_identity = normalized.get(sample.normalized_identity)
        if prior_identity is not None:
            prior_label, prior_split = prior_identity
            if prior_label != sample.label:
                raise EvaluationError("EVAL_CONFLICTING_LABEL")
            if prior_split != split:
                raise EvaluationError("EVAL_CROSS_SPLIT_DUPLICATE")
        else:
            normalized[sample.normalized_identity] = (sample.label, split)
        prior_family_split = families.get(sample.family_id)
        if prior_family_split is not None and prior_family_split != split:
            raise EvaluationError("EVAL_FAMILY_LEAKAGE")
        families[sample.family_id] = split
    if any(labels != set(CLASS_NAMES) for labels in labels_by_split.values()):
        raise EvaluationError("EVAL_MISSING_SPLIT_CLASS")


def load_dataset_snapshot(repository_root: Path, snapshot_path: Path) -> DatasetSnapshot:
    snapshot, _ = _canonical_object(snapshot_path)
    _exact_keys(
        snapshot,
        {
            "corpusPath",
            "corpusSha256",
            "datasetSha256",
            "datasetVersion",
            "schemaVersion",
            "splitManifestPath",
            "splitSha256",
        },
        "EVAL_INVALID_SNAPSHOT",
    )
    if snapshot["schemaVersion"] != SNAPSHOT_SCHEMA_VERSION:
        raise EvaluationError("EVAL_INVALID_SNAPSHOT")
    dataset_version = _required_string(snapshot["datasetVersion"], "EVAL_INVALID_SNAPSHOT")
    if dataset_version != DATASET_VERSION:
        raise EvaluationError("EVAL_INVALID_SNAPSHOT")
    corpus_path = _portable_path(repository_root, snapshot["corpusPath"], EVALUATION_PREFIX)
    split_path = _portable_path(repository_root, snapshot["splitManifestPath"], EVALUATION_PREFIX)
    samples, corpus_sha256 = _load_corpus(repository_root, corpus_path)
    assignments, split_sha256 = _load_split(split_path, {sample.sample_id for sample in samples})
    if snapshot["corpusSha256"] != corpus_sha256 or snapshot["splitSha256"] != split_sha256:
        raise EvaluationError("EVAL_SNAPSHOT_COMPONENT_DIGEST_MISMATCH")
    dataset_payload = {
        "corpusSha256": corpus_sha256,
        "datasetVersion": dataset_version,
        "schemaVersion": SNAPSHOT_SCHEMA_VERSION,
        "splitSha256": split_sha256,
    }
    dataset_sha256 = sha256_bytes(canonical_json_bytes(dataset_payload))
    if snapshot["datasetSha256"] != dataset_sha256:
        raise EvaluationError("EVAL_DATASET_DIGEST_MISMATCH")
    _validate_leakage(samples, assignments)
    return DatasetSnapshot(
        dataset_version=dataset_version,
        corpus_sha256=corpus_sha256,
        split_sha256=split_sha256,
        dataset_sha256=dataset_sha256,
        samples=samples,
        assignments=assignments,
    )


def load_evaluation_policy(path: Path) -> EvaluationPolicy:
    value, raw = _canonical_object(path)
    required = {
        "absoluteGates",
        "abstention",
        "championRelativeLimits",
        "classes",
        "determinism",
        "metricDefinitions",
        "pipelineVersion",
        "policyVersion",
        "preprocessingVersion",
        "schemaVersion",
        "scoreQuality",
    }
    _exact_keys(value, required, "EVAL_INVALID_POLICY")
    if (
        value["schemaVersion"] != POLICY_SCHEMA_VERSION
        or value["classes"] != list(CLASS_NAMES)
        or value["policyVersion"] != POLICY_VERSION
        or value["preprocessingVersion"] != PREPROCESSING_VERSION
        or value["pipelineVersion"] != PIPELINE_VERSION
        or value["abstention"] != {"allowed": False, "failureCode": "EVAL_ABSTENTION_NOT_ALLOWED"}
        or value["determinism"] != {"canonicalReportByteDriftMaximum": 0, "metricDecimalPlaces": 8}
    ):
        raise EvaluationError("EVAL_INVALID_POLICY")
    score_quality = value["scoreQuality"]
    if (
        not isinstance(score_quality, dict)
        or set(score_quality) != {"calibrationClaim", "measure"}
        or score_quality.get("calibrationClaim") is not False
        or score_quality.get("measure") != "meanTrueLabelModelScore"
    ):
        raise EvaluationError("EVAL_INVALID_POLICY")
    absolute = value["absoluteGates"]
    relative = value["championRelativeLimits"]
    if (
        not isinstance(absolute, dict)
        or set(absolute)
        != {
            "macroF1Minimum",
            "meanTrueLabelModelScoreMinimum",
            "perClassRecallMinimum",
            "processedFractionMinimum",
            "sanitizedFailureCountMaximum",
        }
        or not isinstance(relative, dict)
        or set(relative)
        != {
            "macroF1RegressionMaximum",
            "meanTrueLabelModelScoreRegressionMaximum",
            "perClassRecallRegressionMaximum",
        }
    ):
        raise EvaluationError("EVAL_INVALID_POLICY")
    for metrics in (absolute, relative):
        if any(
            isinstance(number, bool)
            or not isinstance(number, (int, float))
            or not math.isfinite(number)
            or not 0 <= number <= 1
            for number in metrics.values()
        ):
            raise EvaluationError("EVAL_INVALID_POLICY")
    if (
        not isinstance(value["metricDefinitions"], dict)
        or set(value["metricDefinitions"])
        != {
            "macroF1",
            "meanTrueLabelModelScore",
            "perClassPrecision",
            "perClassRecall",
            "perClassF1",
        }
        or not all(
            isinstance(definition, str) and definition
            for definition in value["metricDefinitions"].values()
        )
    ):
        raise EvaluationError("EVAL_INVALID_POLICY")
    return EvaluationPolicy(value=value, sha256=sha256_bytes(raw))


def _rounded(value: float) -> float:
    if not math.isfinite(value):
        raise EvaluationError("EVAL_NONFINITE_METRIC")
    return float(f"{value:.8f}")


def _contains_nonfinite(value: object) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, dict):
        return any(_contains_nonfinite(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_nonfinite(item) for item in value)
    return False


def _validate_json_schema(
    value: dict[str, Any],
    schema_path: Path,
    *,
    invalid_schema_code: str,
    violation_code: str,
) -> None:
    schema, _ = _canonical_object(schema_path)
    try:
        Draft202012Validator.check_schema(schema)
        errors = list(Draft202012Validator(schema).iter_errors(value))
    except Exception as error:  # jsonschema exposes multiple schema error subclasses
        raise EvaluationError(invalid_schema_code) from error
    if errors:
        raise EvaluationError(violation_code)


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _classification_metrics(
    confusion: dict[str, dict[str, int]],
) -> tuple[dict[str, dict[str, float]], float]:
    per_class: dict[str, dict[str, float]] = {}
    for label in CLASS_NAMES:
        true_positive = confusion[label][label]
        predicted_total = sum(confusion[actual][label] for actual in CLASS_NAMES)
        actual_total = sum(confusion[label].values())
        precision = _ratio(true_positive, predicted_total)
        recall = _ratio(true_positive, actual_total)
        f1 = _ratio(2 * precision * recall, precision + recall)
        per_class[label] = {
            "f1": _rounded(f1),
            "precision": _rounded(precision),
            "recall": _rounded(recall),
        }
    macro_f1 = _rounded(sum(item["f1"] for item in per_class.values()) / len(CLASS_NAMES))
    return per_class, macro_f1


def _absolute_gate_results(
    policy: EvaluationPolicy,
    *,
    macro_f1: float,
    mean_score: float,
    per_class: dict[str, dict[str, float]],
    processed_fraction: float,
    failure_count: int,
) -> dict[str, bool]:
    absolute = cast(dict[str, float], policy.value["absoluteGates"])
    return {
        "macroF1": macro_f1 >= absolute["macroF1Minimum"],
        "meanTrueLabelModelScore": mean_score >= absolute["meanTrueLabelModelScoreMinimum"],
        "perClassRecall": min(item["recall"] for item in per_class.values())
        >= absolute["perClassRecallMinimum"],
        "processedFraction": processed_fraction >= absolute["processedFractionMinimum"],
        "sanitizedFailureCount": failure_count <= absolute["sanitizedFailureCountMaximum"],
    }


def evaluate_model(
    snapshot: DatasetSnapshot,
    policy: EvaluationPolicy,
    classifier: DocumentClassifier,
    *,
    evaluation_role: str,
    model_name: str,
    model_version: str,
) -> dict[str, Any]:
    if evaluation_role not in {"champion-baseline", "candidate"}:
        raise EvaluationError("EVAL_INVALID_ROLE")
    if not model_name or not model_version:
        raise EvaluationError("EVAL_INVALID_MODEL_IDENTITY")
    if classifier.checksum is None or len(classifier.checksum) != 64:
        raise EvaluationError("EVAL_UNVERIFIED_ARTIFACT")
    test_samples = snapshot.samples_for("test")
    if not test_samples or {sample.label for sample in test_samples} != set(CLASS_NAMES):
        raise EvaluationError("EVAL_MISSING_TEST_CLASS")
    confusion = {actual: {predicted: 0 for predicted in CLASS_NAMES} for actual in CLASS_NAMES}
    sample_outcomes: list[dict[str, Any]] = []
    for sample in test_samples:
        try:
            result = classifier.classify(sample.text)
        except ModelArtifactError as error:
            raise EvaluationError("EVAL_INFERENCE_FAILURE") from error
        if (
            result.classification not in CLASS_NAMES
            or not math.isfinite(result.confidence)
            or not 0.0 <= result.confidence <= 1.0
        ):
            raise EvaluationError("EVAL_INVALID_PREDICTION")
        if result.model_version != model_version:
            raise EvaluationError("EVAL_MODEL_IDENTITY_MISMATCH")
        confusion[sample.label][result.classification] += 1
        true_label_score = _rounded(
            result.confidence if result.classification == sample.label else 1.0 - result.confidence
        )
        sample_outcomes.append(
            {
                "prediction": result.classification,
                "sampleId": sample.sample_id,
                "status": "accepted",
                "trueLabel": sample.label,
                "trueLabelModelScore": true_label_score,
            }
        )

    per_class, macro_f1 = _classification_metrics(confusion)
    mean_score = _rounded(
        sum(cast(float, outcome["trueLabelModelScore"]) for outcome in sample_outcomes)
        / len(sample_outcomes)
    )
    gate_results = _absolute_gate_results(
        policy,
        macro_f1=macro_f1,
        mean_score=mean_score,
        per_class=per_class,
        processed_fraction=1.0,
        failure_count=0,
    )
    report: dict[str, Any] = {
        "absoluteGateResults": gate_results,
        "absoluteGatesPassed": all(gate_results.values()),
        "artifactSha256": classifier.checksum,
        "classes": list(CLASS_NAMES),
        "confusionMatrix": confusion,
        "corpusSha256": snapshot.corpus_sha256,
        "datasetSha256": snapshot.dataset_sha256,
        "datasetVersion": snapshot.dataset_version,
        "evaluationRole": evaluation_role,
        "failureCounts": {},
        "failures": [],
        "metrics": {
            "macroF1": macro_f1,
            "meanTrueLabelModelScore": mean_score,
            "perClass": per_class,
        },
        "modelName": model_name,
        "modelVersion": model_version,
        "pipelineVersion": policy.value["pipelineVersion"],
        "policySha256": policy.sha256,
        "policyVersion": policy.version,
        "preprocessingVersion": policy.value["preprocessingVersion"],
        "processedSampleCount": len(test_samples),
        "reportSchemaVersion": REPORT_SCHEMA_VERSION,
        "sampleOutcomes": sample_outcomes,
        "splitSha256": snapshot.split_sha256,
        "testSampleIds": [sample.sample_id for sample in test_samples],
        "totalSampleCount": len(test_samples),
    }
    report["reportSha256"] = sha256_bytes(canonical_json_bytes(report))
    return report


def evaluate_champion(
    snapshot: DatasetSnapshot,
    policy: EvaluationPolicy,
    classifier: DocumentClassifier,
) -> dict[str, Any]:
    return evaluate_model(
        snapshot,
        policy,
        classifier,
        evaluation_role="champion-baseline",
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
    )


def validate_evaluation_report(
    report: dict[str, Any],
    schema_path: Path,
    snapshot: DatasetSnapshot,
    policy: EvaluationPolicy,
    artifact_sha256: str,
    *,
    evaluation_role: str = "champion-baseline",
    model_name: str = MODEL_NAME,
    model_version: str = MODEL_VERSION,
) -> None:
    if _contains_nonfinite(report):
        raise EvaluationError("EVAL_NONFINITE_METRIC")
    _validate_json_schema(
        report,
        schema_path,
        invalid_schema_code="EVAL_INVALID_REPORT_SCHEMA",
        violation_code="EVAL_REPORT_SCHEMA_VIOLATION",
    )
    if report.get("artifactSha256") != artifact_sha256:
        raise EvaluationError("EVAL_REPORT_ARTIFACT_MISMATCH")
    expected_samples = snapshot.samples_for("test")
    expected_ids = [sample.sample_id for sample in expected_samples]
    expected_identity = {
        "corpusSha256": snapshot.corpus_sha256,
        "datasetSha256": snapshot.dataset_sha256,
        "datasetVersion": snapshot.dataset_version,
        "evaluationRole": evaluation_role,
        "modelName": model_name,
        "modelVersion": model_version,
        "pipelineVersion": policy.value["pipelineVersion"],
        "policySha256": policy.sha256,
        "policyVersion": policy.version,
        "preprocessingVersion": policy.value["preprocessingVersion"],
        "splitSha256": snapshot.split_sha256,
        "testSampleIds": expected_ids,
        "totalSampleCount": len(expected_ids),
    }
    if any(report.get(key) != value for key, value in expected_identity.items()):
        raise EvaluationError("EVAL_REPORT_LINEAGE_MISMATCH")
    if (
        report.get("processedSampleCount") != len(expected_ids)
        or report.get("failureCounts") != {}
        or report.get("failures") != []
    ):
        raise EvaluationError("EVAL_INCOMPLETE_REPORT")
    outcomes = cast(list[dict[str, Any]], report["sampleOutcomes"])
    if (
        len(outcomes) != len(expected_samples)
        or [outcome["sampleId"] for outcome in outcomes] != expected_ids
    ):
        raise EvaluationError("EVAL_REPORT_OUTCOME_MISMATCH")
    expected_confusion = {
        actual: {predicted: 0 for predicted in CLASS_NAMES} for actual in CLASS_NAMES
    }
    true_label_scores: list[float] = []
    for sample, outcome in zip(expected_samples, outcomes, strict=True):
        if (
            outcome["trueLabel"] != sample.label
            or outcome["status"] != "accepted"
            or outcome["prediction"] not in CLASS_NAMES
        ):
            raise EvaluationError("EVAL_REPORT_OUTCOME_MISMATCH")
        score = cast(float, outcome["trueLabelModelScore"])
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise EvaluationError("EVAL_REPORT_OUTCOME_MISMATCH")
        expected_confusion[sample.label][cast(str, outcome["prediction"])] += 1
        true_label_scores.append(score)
    if report["confusionMatrix"] != expected_confusion:
        raise EvaluationError("EVAL_REPORT_CONFUSION_MISMATCH")
    expected_per_class, expected_macro_f1 = _classification_metrics(expected_confusion)
    expected_mean_score = _rounded(sum(true_label_scores) / len(true_label_scores))
    metrics = cast(dict[str, Any], report["metrics"])
    expected_metrics = {
        "macroF1": expected_macro_f1,
        "meanTrueLabelModelScore": expected_mean_score,
        "perClass": expected_per_class,
    }
    if metrics != expected_metrics:
        raise EvaluationError("EVAL_REPORT_METRIC_MISMATCH")
    expected_gates = _absolute_gate_results(
        policy,
        macro_f1=expected_macro_f1,
        mean_score=expected_mean_score,
        per_class=expected_per_class,
        processed_fraction=1.0,
        failure_count=0,
    )
    if report["absoluteGateResults"] != expected_gates or report["absoluteGatesPassed"] is not all(
        expected_gates.values()
    ):
        raise EvaluationError("EVAL_REPORT_GATE_MISMATCH")
    supplied_digest = report.get("reportSha256")
    unsigned = {key: value for key, value in report.items() if key != "reportSha256"}
    if supplied_digest != sha256_bytes(canonical_json_bytes(unsigned)):
        raise EvaluationError("EVAL_REPORT_DIGEST_MISMATCH")


def load_evaluation_report(
    path: Path,
    schema_path: Path,
    snapshot: DatasetSnapshot,
    policy: EvaluationPolicy,
    artifact_sha256: str,
    *,
    evaluation_role: str,
    model_name: str,
    model_version: str,
) -> tuple[dict[str, Any], bytes]:
    value, raw = _canonical_object(path)
    validate_evaluation_report(
        value,
        schema_path,
        snapshot,
        policy,
        artifact_sha256,
        evaluation_role=evaluation_role,
        model_name=model_name,
        model_version=model_version,
    )
    return value, raw


def load_champion_baseline(
    path: Path,
    schema_path: Path,
    snapshot: DatasetSnapshot,
    policy: EvaluationPolicy,
    artifact_sha256: str,
) -> tuple[dict[str, Any], bytes]:
    return load_evaluation_report(
        path,
        schema_path,
        snapshot,
        policy,
        artifact_sha256,
        evaluation_role="champion-baseline",
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
    )


def compare_candidate(
    champion_report: dict[str, Any],
    candidate_report: dict[str, Any],
    report_schema_path: Path,
    snapshot: DatasetSnapshot,
    policy: EvaluationPolicy,
    champion_artifact_sha256: str,
    candidate_artifact_sha256: str,
    *,
    candidate_model_name: str,
    candidate_model_version: str,
) -> dict[str, Any]:
    validate_evaluation_report(
        champion_report,
        report_schema_path,
        snapshot,
        policy,
        champion_artifact_sha256,
    )
    validate_evaluation_report(
        candidate_report,
        report_schema_path,
        snapshot,
        policy,
        candidate_artifact_sha256,
        evaluation_role="candidate",
        model_name=candidate_model_name,
        model_version=candidate_model_version,
    )
    champion_metrics = cast(dict[str, Any], champion_report["metrics"])
    candidate_metrics = cast(dict[str, Any], candidate_report["metrics"])
    relative_limits = cast(dict[str, float], policy.value["championRelativeLimits"])
    macro_f1_regression = _rounded(champion_metrics["macroF1"] - candidate_metrics["macroF1"])
    mean_score_regression = _rounded(
        champion_metrics["meanTrueLabelModelScore"] - candidate_metrics["meanTrueLabelModelScore"]
    )
    champion_per_class = cast(dict[str, dict[str, float]], champion_metrics["perClass"])
    candidate_per_class = cast(dict[str, dict[str, float]], candidate_metrics["perClass"])
    recall_regressions = {
        label: _rounded(champion_per_class[label]["recall"] - candidate_per_class[label]["recall"])
        for label in CLASS_NAMES
    }
    relative_results: dict[str, Any] = {
        "macroF1": macro_f1_regression <= relative_limits["macroF1RegressionMaximum"],
        "meanTrueLabelModelScore": mean_score_regression
        <= relative_limits["meanTrueLabelModelScoreRegressionMaximum"],
        "perClassRecall": {
            label: regression <= relative_limits["perClassRecallRegressionMaximum"]
            for label, regression in recall_regressions.items()
        },
    }
    rejection_reasons: list[str] = []
    if candidate_report["absoluteGatesPassed"] is not True:
        rejection_reasons.append("EVAL_CANDIDATE_ABSOLUTE_GATES_FAILED")
    if relative_results["macroF1"] is not True:
        rejection_reasons.append("EVAL_CANDIDATE_MACRO_F1_REGRESSION")
    if relative_results["meanTrueLabelModelScore"] is not True:
        rejection_reasons.append("EVAL_CANDIDATE_MEAN_SCORE_REGRESSION")
    per_class_results = cast(dict[str, bool], relative_results["perClassRecall"])
    for label in CLASS_NAMES:
        if per_class_results[label] is not True:
            rejection_reasons.append(f"EVAL_CANDIDATE_{label.upper()}_RECALL_REGRESSION")

    comparison: dict[str, Any] = {
        "absoluteGatesPassed": candidate_report["absoluteGatesPassed"],
        "candidate": {
            "artifactSha256": candidate_artifact_sha256,
            "modelName": candidate_model_name,
            "modelVersion": candidate_model_version,
            "reportSha256": candidate_report["reportSha256"],
        },
        "champion": {
            "artifactSha256": champion_artifact_sha256,
            "modelName": champion_report["modelName"],
            "modelVersion": champion_report["modelVersion"],
            "reportSha256": champion_report["reportSha256"],
        },
        "comparisonSchemaVersion": COMPARISON_SCHEMA_VERSION,
        "datasetSha256": snapshot.dataset_sha256,
        "eligible": not rejection_reasons,
        "policySha256": policy.sha256,
        "regressions": {
            "macroF1": macro_f1_regression,
            "meanTrueLabelModelScore": mean_score_regression,
            "perClassRecall": recall_regressions,
        },
        "rejectionReasons": rejection_reasons,
        "relativeGateResults": relative_results,
        "splitSha256": snapshot.split_sha256,
    }
    comparison["comparisonSha256"] = sha256_bytes(canonical_json_bytes(comparison))
    return comparison


def validate_candidate_comparison(
    comparison: dict[str, Any],
    comparison_schema_path: Path,
    champion_report: dict[str, Any],
    candidate_report: dict[str, Any],
    report_schema_path: Path,
    snapshot: DatasetSnapshot,
    policy: EvaluationPolicy,
    champion_artifact_sha256: str,
    candidate_artifact_sha256: str,
    *,
    candidate_model_name: str,
    candidate_model_version: str,
) -> None:
    if _contains_nonfinite(comparison):
        raise EvaluationError("EVAL_NONFINITE_COMPARISON")
    _validate_json_schema(
        comparison,
        comparison_schema_path,
        invalid_schema_code="EVAL_INVALID_COMPARISON_SCHEMA",
        violation_code="EVAL_COMPARISON_SCHEMA_VIOLATION",
    )
    supplied_digest = comparison.get("comparisonSha256")
    unsigned = {key: value for key, value in comparison.items() if key != "comparisonSha256"}
    if supplied_digest != sha256_bytes(canonical_json_bytes(unsigned)):
        raise EvaluationError("EVAL_COMPARISON_DIGEST_MISMATCH")
    expected = compare_candidate(
        champion_report,
        candidate_report,
        report_schema_path,
        snapshot,
        policy,
        champion_artifact_sha256,
        candidate_artifact_sha256,
        candidate_model_name=candidate_model_name,
        candidate_model_version=candidate_model_version,
    )
    if comparison != expected:
        raise EvaluationError("EVAL_COMPARISON_MISMATCH")


def load_candidate_comparison(
    path: Path,
    comparison_schema_path: Path,
    champion_report: dict[str, Any],
    candidate_report: dict[str, Any],
    report_schema_path: Path,
    snapshot: DatasetSnapshot,
    policy: EvaluationPolicy,
    champion_artifact_sha256: str,
    candidate_artifact_sha256: str,
    *,
    candidate_model_name: str,
    candidate_model_version: str,
) -> tuple[dict[str, Any], bytes]:
    value, raw = _canonical_object(path)
    validate_candidate_comparison(
        value,
        comparison_schema_path,
        champion_report,
        candidate_report,
        report_schema_path,
        snapshot,
        policy,
        champion_artifact_sha256,
        candidate_artifact_sha256,
        candidate_model_name=candidate_model_name,
        candidate_model_version=candidate_model_version,
    )
    return value, raw
