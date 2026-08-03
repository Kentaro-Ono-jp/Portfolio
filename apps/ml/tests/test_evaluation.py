from __future__ import annotations

import hashlib
import json
import math
import shutil
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

from reactorfront_ml.domain import ClassificationResult
from reactorfront_ml.evaluation import (
    DatasetSnapshot,
    EvaluationError,
    EvaluationPolicy,
    canonical_json_bytes,
    evaluate_champion,
    load_champion_baseline,
    load_dataset_snapshot,
    load_evaluation_policy,
    sha256_bytes,
    validate_evaluation_report,
)
from reactorfront_ml.model import DocumentClassifier, ModelArtifactError, generate_artifact

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EVALUATION_ROOT = REPOSITORY_ROOT / "apps" / "ml" / "evaluation"
SNAPSHOT_PATH = EVALUATION_ROOT / "corpus" / "v1" / "snapshot.json"
POLICY_PATH = EVALUATION_ROOT / "policy-v1.json"
SCHEMA_PATH = EVALUATION_ROOT / "evaluation-report-v1.schema.json"
BASELINE_PATH = EVALUATION_ROOT / "champion-baseline-v1.json"
TRAINING_DATA_PATH = REPOSITORY_ROOT / "apps" / "ml" / "data" / "training.json"


def read_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_bytes()))


def write_json(path: Path, value: object) -> None:
    path.write_bytes(canonical_json_bytes(value))


def copied_repository(tmp_path: Path) -> Path:
    destination = tmp_path / "repository" / "apps" / "ml" / "evaluation"
    destination.parent.mkdir(parents=True)
    shutil.copytree(EVALUATION_ROOT, destination)
    return tmp_path / "repository"


def refresh_snapshot(repository_root: Path) -> None:
    evaluation_root = repository_root / "apps" / "ml" / "evaluation"
    corpus_path = evaluation_root / "corpus" / "v1" / "corpus.json"
    split_path = evaluation_root / "corpus" / "v1" / "split.json"
    snapshot_path = evaluation_root / "corpus" / "v1" / "snapshot.json"
    snapshot = read_json(snapshot_path)
    snapshot["corpusSha256"] = sha256_bytes(corpus_path.read_bytes())
    snapshot["splitSha256"] = sha256_bytes(split_path.read_bytes())
    payload = {
        "corpusSha256": snapshot["corpusSha256"],
        "datasetVersion": snapshot["datasetVersion"],
        "schemaVersion": snapshot["schemaVersion"],
        "splitSha256": snapshot["splitSha256"],
    }
    snapshot["datasetSha256"] = sha256_bytes(canonical_json_bytes(payload))
    write_json(snapshot_path, snapshot)


def mutate_corpus(
    repository_root: Path,
    mutation: Callable[[dict[str, Any], Path], None],
) -> Path:
    path = repository_root / "apps" / "ml" / "evaluation" / "corpus" / "v1" / "corpus.json"
    value = read_json(path)
    mutation(value, repository_root)
    write_json(path, value)
    refresh_snapshot(repository_root)
    return repository_root / "apps" / "ml" / "evaluation" / "corpus" / "v1" / "snapshot.json"


def mutate_split(repository_root: Path, mutation: Callable[[dict[str, Any]], None]) -> Path:
    path = repository_root / "apps" / "ml" / "evaluation" / "corpus" / "v1" / "split.json"
    value = read_json(path)
    mutation(value)
    write_json(path, value)
    refresh_snapshot(repository_root)
    return repository_root / "apps" / "ml" / "evaluation" / "corpus" / "v1" / "snapshot.json"


def build_classifier(tmp_path: Path) -> DocumentClassifier:
    generated = generate_artifact(TRAINING_DATA_PATH)
    artifact_path = tmp_path / "model.json"
    checksum_path = tmp_path / "model.sha256"
    artifact_path.write_bytes(generated.content)
    checksum_path.write_text(f"{generated.sha256}\n", encoding="utf-8")
    return DocumentClassifier(artifact_path=artifact_path, checksum_path=checksum_path)


def report_context(
    tmp_path: Path,
) -> tuple[DatasetSnapshot, EvaluationPolicy, DocumentClassifier, dict[str, Any]]:
    snapshot = load_dataset_snapshot(REPOSITORY_ROOT, SNAPSHOT_PATH)
    policy = load_evaluation_policy(POLICY_PATH)
    classifier = build_classifier(tmp_path)
    return snapshot, policy, classifier, evaluate_champion(snapshot, policy, classifier)


def assert_snapshot_error(repository_root: Path, snapshot_path: Path, code: str) -> None:
    with pytest.raises(EvaluationError, match=code) as raised:
        load_dataset_snapshot(repository_root, snapshot_path)
    assert raised.value.code == code


def test_snapshot_is_canonical_complete_and_family_disjoint() -> None:
    snapshot = load_dataset_snapshot(REPOSITORY_ROOT, SNAPSHOT_PATH)

    assert snapshot.dataset_version == "reactorfront-synthetic-documents-v1"
    assert len(snapshot.samples) == 18
    assert {
        split: len(snapshot.samples_for(split)) for split in ("train", "validation", "test")
    } == {
        "train": 12,
        "validation": 2,
        "test": 4,
    }
    for split in ("train", "validation", "test"):
        assert {sample.label for sample in snapshot.samples_for(split)} == {"invoice", "report"}
    assert len({sample.source_sha256 for sample in snapshot.samples}) == 18
    assert all(sample.source_path.is_file() for sample in snapshot.samples)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (
            lambda value, root: value["samples"][1].update(
                sampleId=value["samples"][0]["sampleId"]
            ),
            "EVAL_DUPLICATE_SAMPLE_ID",
        ),
        (
            lambda value, root: value["samples"][1].update(
                sourceSha256=value["samples"][0]["sourceSha256"]
            ),
            "EVAL_DUPLICATE_SOURCE_DIGEST",
        ),
        (
            lambda value, root: value["samples"][0].update(provenance="runtime-review"),
            "EVAL_INVALID_PROVENANCE",
        ),
        (lambda value, root: value["samples"][0].update(label="other"), "EVAL_INVALID_LABEL"),
        (
            lambda value, root: value["samples"][0].update(sourceSha256="invalid"),
            "EVAL_INVALID_SOURCE_DIGEST",
        ),
        (
            lambda value, root: value["samples"][0].update(path="../private.txt"),
            "EVAL_UNSAFE_SOURCE_PATH",
        ),
        (
            lambda value, root: value["samples"][0].update(
                path="apps/ml/evaluation/corpus/v1/sources/missing.txt"
            ),
            "EVAL_MISSING_OR_INVALID_SOURCE",
        ),
        (lambda value, root: value["samples"].reverse(), "EVAL_NONCANONICAL_SAMPLE_ORDER"),
    ],
)
def test_corpus_metadata_mutations_fail_closed(
    tmp_path: Path,
    mutation: Callable[[dict[str, Any], Path], None],
    code: str,
) -> None:
    repository_root = copied_repository(tmp_path)
    snapshot_path = mutate_corpus(repository_root, mutation)

    assert_snapshot_error(repository_root, snapshot_path, code)


def replace_source(
    corpus: dict[str, Any],
    repository_root: Path,
    sample_id: str,
    source_text: str,
) -> None:
    sample = next(item for item in corpus["samples"] if item["sampleId"] == sample_id)
    source_path = repository_root / Path(*Path(sample["path"]).parts)
    source_path.write_bytes(source_text.encode())
    sample["sourceSha256"] = hashlib.sha256(source_text.encode()).hexdigest()


@pytest.mark.parametrize(
    ("sample_id", "copied_sample_id", "code"),
    [
        ("invoice-validation-001", "report-validation-001", "EVAL_CONFLICTING_LABEL"),
        ("invoice-validation-001", "invoice-test-001", "EVAL_CROSS_SPLIT_DUPLICATE"),
    ],
)
def test_normalized_identity_leakage_fails_closed(
    tmp_path: Path,
    sample_id: str,
    copied_sample_id: str,
    code: str,
) -> None:
    repository_root = copied_repository(tmp_path)

    def mutation(corpus: dict[str, Any], root: Path) -> None:
        copied = next(item for item in corpus["samples"] if item["sampleId"] == copied_sample_id)
        copied_path = root / Path(*Path(copied["path"]).parts)
        replace_source(corpus, root, sample_id, copied_path.read_text(encoding="utf-8").upper())

    snapshot_path = mutate_corpus(repository_root, mutation)

    assert_snapshot_error(repository_root, snapshot_path, code)


def test_family_leakage_fails_closed(tmp_path: Path) -> None:
    repository_root = copied_repository(tmp_path)

    def mutation(corpus: dict[str, Any], root: Path) -> None:
        sample = next(
            item for item in corpus["samples"] if item["sampleId"] == "invoice-validation-001"
        )
        sample["familyId"] = "invoice-test-v1"

    snapshot_path = mutate_corpus(repository_root, mutation)
    assert_snapshot_error(repository_root, snapshot_path, "EVAL_FAMILY_LEAKAGE")


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (
            lambda value: value["assignments"].append(deepcopy(value["assignments"][0])),
            "EVAL_DUPLICATE_ASSIGNMENT",
        ),
        (lambda value: value["assignments"].pop(), "EVAL_INCOMPLETE_ASSIGNMENTS"),
        (lambda value: value["assignments"][0].update(split="other"), "EVAL_INVALID_ASSIGNMENT"),
        (lambda value: value["assignments"].reverse(), "EVAL_NONCANONICAL_ASSIGNMENT_ORDER"),
        (
            lambda value: next(
                item for item in value["assignments"] if item["sampleId"] == "report-validation-001"
            ).update(split="train"),
            "EVAL_MISSING_SPLIT_CLASS",
        ),
    ],
)
def test_split_mutations_fail_closed(
    tmp_path: Path,
    mutation: Callable[[dict[str, Any]], None],
    code: str,
) -> None:
    repository_root = copied_repository(tmp_path)
    snapshot_path = mutate_split(repository_root, mutation)

    assert_snapshot_error(repository_root, snapshot_path, code)


def test_source_content_and_snapshot_digest_mutations_fail_closed(tmp_path: Path) -> None:
    repository_root = copied_repository(tmp_path)
    corpus = read_json(repository_root / "apps/ml/evaluation/corpus/v1/corpus.json")
    sample = corpus["samples"][0]
    source_path = repository_root / Path(*Path(sample["path"]).parts)
    source_path.write_text("mutated source\n", encoding="utf-8")
    snapshot_path = repository_root / "apps/ml/evaluation/corpus/v1/snapshot.json"
    assert_snapshot_error(repository_root, snapshot_path, "EVAL_SOURCE_DIGEST_MISMATCH")

    repository_root = copied_repository(tmp_path / "second")
    snapshot_path = repository_root / "apps/ml/evaluation/corpus/v1/snapshot.json"
    snapshot = read_json(snapshot_path)
    snapshot["datasetSha256"] = "0" * 64
    write_json(snapshot_path, snapshot)
    assert_snapshot_error(repository_root, snapshot_path, "EVAL_DATASET_DIGEST_MISMATCH")


def test_noncanonical_json_and_source_fail_closed(tmp_path: Path) -> None:
    repository_root = copied_repository(tmp_path)
    corpus_path = repository_root / "apps/ml/evaluation/corpus/v1/corpus.json"
    corpus_path.write_text(json.dumps(read_json(corpus_path)), encoding="utf-8")
    snapshot_path = repository_root / "apps/ml/evaluation/corpus/v1/snapshot.json"
    assert_snapshot_error(repository_root, snapshot_path, "EVAL_NONCANONICAL_JSON")

    repository_root = copied_repository(tmp_path / "second")

    def mutation(corpus: dict[str, Any], root: Path) -> None:
        replace_source(corpus, root, "invoice-validation-001", " padded source \n")

    snapshot_path = mutate_corpus(repository_root, mutation)
    assert_snapshot_error(repository_root, snapshot_path, "EVAL_NONCANONICAL_SOURCE")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(schemaVersion=0),
        lambda value: value.update(classes=["other"]),
        lambda value: value.update(abstention={"allowed": True}),
        lambda value: value.update(determinism={"canonicalReportByteDriftMaximum": 1}),
        lambda value: value.update(
            scoreQuality={"calibrationClaim": True, "measure": "meanTrueLabelModelScore"}
        ),
        lambda value: value["absoluteGates"].update(macroF1Minimum=-1),
        lambda value: value["absoluteGates"].update(unexpectedGate=0),
        lambda value: value.update(metricDefinitions={}),
        lambda value: value["metricDefinitions"].update(macroF1=1),
    ],
)
def test_invalid_policy_fails_closed(
    tmp_path: Path, mutation: Callable[[dict[str, Any]], None]
) -> None:
    value = read_json(POLICY_PATH)
    mutation(value)
    path = tmp_path / "policy.json"
    write_json(path, value)

    with pytest.raises(EvaluationError, match="EVAL_INVALID_POLICY"):
        load_evaluation_policy(path)


def test_canonical_json_rejects_nonfinite_or_unserializable_values() -> None:
    with pytest.raises(EvaluationError, match="EVAL_NONCANONICAL_VALUE"):
        canonical_json_bytes({"value": math.nan})
    with pytest.raises(EvaluationError, match="EVAL_NONCANONICAL_VALUE"):
        canonical_json_bytes(object())


def test_champion_report_is_complete_canonical_and_equal_to_baseline(tmp_path: Path) -> None:
    snapshot, policy, classifier, first = report_context(tmp_path)
    second = evaluate_champion(snapshot, policy, classifier)

    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert first["absoluteGatesPassed"] is True
    assert first["metrics"] == {
        "macroF1": 1.0,
        "meanTrueLabelModelScore": 0.99982216,
        "perClass": {
            "invoice": {"f1": 1.0, "precision": 1.0, "recall": 1.0},
            "report": {"f1": 1.0, "precision": 1.0, "recall": 1.0},
        },
    }
    assert first["processedSampleCount"] == first["totalSampleCount"] == 4
    assert first["failureCounts"] == {}
    validate_evaluation_report(first, SCHEMA_PATH, snapshot, policy, classifier.checksum)
    baseline, baseline_bytes = load_champion_baseline(
        BASELINE_PATH,
        SCHEMA_PATH,
        snapshot,
        policy,
        classifier.checksum,
    )
    assert baseline == first
    assert baseline_bytes == canonical_json_bytes(first)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda report: report.pop("metrics"), "EVAL_REPORT_SCHEMA_VIOLATION"),
        (lambda report: report.update(artifactSha256="0" * 64), "EVAL_REPORT_ARTIFACT_MISMATCH"),
        (lambda report: report.update(datasetSha256="0" * 64), "EVAL_REPORT_LINEAGE_MISMATCH"),
        (lambda report: report.update(processedSampleCount=3), "EVAL_INCOMPLETE_REPORT"),
        (
            lambda report: report["confusionMatrix"]["invoice"].update(invoice=1),
            "EVAL_REPORT_CONFUSION_MISMATCH",
        ),
        (lambda report: report["metrics"].update(macroF1=0.5), "EVAL_REPORT_METRIC_MISMATCH"),
        (
            lambda report: report["absoluteGateResults"].update(macroF1=False),
            "EVAL_REPORT_GATE_MISMATCH",
        ),
        (lambda report: report.update(reportSha256="0" * 64), "EVAL_REPORT_DIGEST_MISMATCH"),
    ],
)
def test_report_mutations_fail_closed(
    tmp_path: Path,
    mutation: Callable[[dict[str, Any]], object],
    code: str,
) -> None:
    snapshot, policy, classifier, original = report_context(tmp_path)
    report = deepcopy(original)
    mutation(report)
    if code not in {"EVAL_REPORT_SCHEMA_VIOLATION", "EVAL_REPORT_DIGEST_MISMATCH"}:
        unsigned = {key: value for key, value in report.items() if key != "reportSha256"}
        report["reportSha256"] = sha256_bytes(canonical_json_bytes(unsigned))

    with pytest.raises(EvaluationError, match=code):
        validate_evaluation_report(report, SCHEMA_PATH, snapshot, policy, classifier.checksum)


def test_nonfinite_report_metric_fails_closed(tmp_path: Path) -> None:
    snapshot, policy, classifier, report = report_context(tmp_path)
    report["metrics"]["meanTrueLabelModelScore"] = math.nan

    with pytest.raises(EvaluationError, match="EVAL_NONFINITE_METRIC"):
        validate_evaluation_report(report, SCHEMA_PATH, snapshot, policy, classifier.checksum)


def test_invalid_report_schema_fails_closed(tmp_path: Path) -> None:
    snapshot, policy, classifier, report = report_context(tmp_path)
    schema_path = tmp_path / "schema.json"
    write_json(schema_path, {"type": "unsupported"})

    with pytest.raises(EvaluationError, match="EVAL_INVALID_REPORT_SCHEMA"):
        validate_evaluation_report(report, schema_path, snapshot, policy, classifier.checksum)


class FakeClassifier:
    checksum = "a" * 64

    def __init__(self, result: ClassificationResult | Exception) -> None:
        self.result = result

    def classify(self, text: str) -> ClassificationResult:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.mark.parametrize(
    ("result", "code"),
    [
        (ModelArtifactError("private detail"), "EVAL_INFERENCE_FAILURE"),
        (
            ClassificationResult(classification="other", confidence=0.5, model_version="v"),
            "EVAL_INVALID_PREDICTION",
        ),
        (
            ClassificationResult(classification="invoice", confidence=math.nan, model_version="v"),
            "EVAL_INVALID_PREDICTION",
        ),
    ],
)
def test_prediction_failures_are_sanitized(
    result: ClassificationResult | Exception,
    code: str,
) -> None:
    snapshot = load_dataset_snapshot(REPOSITORY_ROOT, SNAPSHOT_PATH)
    policy = load_evaluation_policy(POLICY_PATH)

    with pytest.raises(EvaluationError, match=code):
        evaluate_champion(snapshot, policy, cast(DocumentClassifier, FakeClassifier(result)))


def test_inaccurate_classifier_produces_complete_failing_gate_report() -> None:
    snapshot = load_dataset_snapshot(REPOSITORY_ROOT, SNAPSHOT_PATH)
    policy = load_evaluation_policy(POLICY_PATH)
    classifier = FakeClassifier(
        ClassificationResult(classification="invoice", confidence=0.9, model_version="v")
    )

    report = evaluate_champion(snapshot, policy, cast(DocumentClassifier, classifier))

    assert report["absoluteGatesPassed"] is False
    assert report["confusionMatrix"]["report"] == {"invoice": 2, "report": 0}
    assert report["metrics"]["perClass"]["report"] == {
        "f1": 0.0,
        "precision": 0.0,
        "recall": 0.0,
    }


def test_unverified_classifier_fails_closed() -> None:
    snapshot = load_dataset_snapshot(REPOSITORY_ROOT, SNAPSHOT_PATH)
    policy = load_evaluation_policy(POLICY_PATH)
    classifier = FakeClassifier(
        ClassificationResult(classification="invoice", confidence=0.9, model_version="v")
    )
    classifier.checksum = ""

    with pytest.raises(EvaluationError, match="EVAL_UNVERIFIED_ARTIFACT"):
        evaluate_champion(snapshot, policy, cast(DocumentClassifier, classifier))
