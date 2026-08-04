from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

import pytest

from reactorfront_ml.candidate import (
    CANDIDATE_MODEL_VERSION,
    build_candidate,
    load_candidate_build_manifest,
)
from reactorfront_ml.domain import ClassificationResult
from reactorfront_ml.evaluation import (
    EvaluationError,
    EvaluationPolicy,
    canonical_json_bytes,
    compare_candidate,
    evaluate_model,
    load_candidate_comparison,
    load_champion_baseline,
    load_dataset_snapshot,
    load_evaluation_policy,
    load_evaluation_report,
    sha256_bytes,
    validate_candidate_comparison,
)
from reactorfront_ml.model import MODEL_NAME, DocumentClassifier, ModelArtifactError

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ML_ROOT = REPOSITORY_ROOT / "apps" / "ml"
EVALUATION_ROOT = ML_ROOT / "evaluation"
SNAPSHOT_PATH = EVALUATION_ROOT / "corpus" / "v1" / "snapshot.json"
POLICY_PATH = EVALUATION_ROOT / "policy-v1.json"
REPORT_SCHEMA_PATH = EVALUATION_ROOT / "evaluation-report-v1.schema.json"
COMPARISON_SCHEMA_PATH = EVALUATION_ROOT / "candidate-comparison-v1.schema.json"
CHAMPION_PATH = EVALUATION_ROOT / "champion-baseline-v1.json"
CANDIDATE_BUILD_PATH = EVALUATION_ROOT / "candidate-build-v1.json"
CANDIDATE_REPORT_PATH = EVALUATION_ROOT / "candidate-report-v1.json"
CANDIDATE_COMPARISON_PATH = EVALUATION_ROOT / "candidate-comparison-v1.json"
DEPENDENCY_LOCK_PATH = ML_ROOT / "uv.lock"
CHAMPION_CHECKSUM_PATH = ML_ROOT / "model.expected.sha256"


def write_json(path: Path, value: object) -> None:
    path.write_bytes(canonical_json_bytes(value))


def candidate_context() -> tuple[Any, EvaluationPolicy, Any]:
    snapshot = load_dataset_snapshot(REPOSITORY_ROOT, SNAPSHOT_PATH)
    policy = load_evaluation_policy(POLICY_PATH)
    return snapshot, policy, build_candidate(snapshot, policy, DEPENDENCY_LOCK_PATH)


def candidate_report(snapshot: Any, policy: EvaluationPolicy, build: Any) -> dict[str, Any]:
    with TemporaryDirectory(prefix="reactorfront-candidate-test-") as directory:
        root = Path(directory)
        artifact_path = root / "model.json"
        checksum_path = root / "model.sha256"
        artifact_path.write_bytes(build.artifact.content)
        checksum_path.write_text(f"{build.artifact.sha256}\n", encoding="utf-8")
        classifier = DocumentClassifier(
            artifact_path=artifact_path,
            checksum_path=checksum_path,
            expected_model_version=CANDIDATE_MODEL_VERSION,
        )
        return evaluate_model(
            snapshot,
            policy,
            classifier,
            evaluation_role="candidate",
            model_name=MODEL_NAME,
            model_version=CANDIDATE_MODEL_VERSION,
        )


def champion_report(snapshot: Any, policy: EvaluationPolicy) -> dict[str, Any]:
    checksum = CHAMPION_CHECKSUM_PATH.read_text(encoding="utf-8").strip()
    value, _ = load_champion_baseline(
        CHAMPION_PATH,
        REPORT_SCHEMA_PATH,
        snapshot,
        policy,
        checksum,
    )
    return value


def test_candidate_build_is_reproducible_and_uses_only_training_split() -> None:
    snapshot, policy, first = candidate_context()
    second = build_candidate(snapshot, policy, DEPENDENCY_LOCK_PATH)

    assert first.artifact.content == second.artifact.content
    assert first.artifact.sha256 == second.artifact.sha256
    assert first.manifest == second.manifest
    assert first.artifact.sha256 == (
        "17006d0e045fdc42547ca0b0dd058eb67532e6967a1136156c51e4cb4c00de09"
    )
    expected_ids = [sample.sample_id for sample in snapshot.samples_for("train")]
    assert first.manifest["training"]["sampleIds"] == expected_ids
    assert first.manifest["training"]["sampleCount"] == 12
    assert first.manifest["confidenceTreatment"] == {
        "calibrationClaim": False,
        "method": "none",
        "validationSampleIds": [],
    }
    artifact = json.loads(first.artifact.content)
    assert artifact["training"]["trainingSampleIds"] == expected_ids
    serialized = canonical_json_bytes(first.manifest).decode()
    assert "validation-001" not in serialized
    assert "test-001" not in serialized


def test_candidate_classifier_requires_the_explicit_candidate_identity(tmp_path: Path) -> None:
    _, _, build = candidate_context()
    artifact_path = tmp_path / "candidate.json"
    checksum_path = tmp_path / "candidate.sha256"
    artifact_path.write_bytes(build.artifact.content)
    checksum_path.write_text(f"{build.artifact.sha256}\n", encoding="utf-8")

    with pytest.raises(ModelArtifactError, match="identity"):
        DocumentClassifier(artifact_path=artifact_path, checksum_path=checksum_path)

    classifier = DocumentClassifier(
        artifact_path=artifact_path,
        checksum_path=checksum_path,
        expected_model_name=MODEL_NAME,
        expected_model_version=CANDIDATE_MODEL_VERSION,
    )
    assert classifier.model_name == MODEL_NAME
    assert classifier.model_version == CANDIDATE_MODEL_VERSION
    assert classifier.classify("invoice subtotal tax amount due").model_version == (
        CANDIDATE_MODEL_VERSION
    )


def test_candidate_build_manifest_is_canonical_and_recomputed(tmp_path: Path) -> None:
    snapshot, policy, build = candidate_context()
    manifest, raw, artifact = load_candidate_build_manifest(
        CANDIDATE_BUILD_PATH,
        snapshot,
        policy,
        DEPENDENCY_LOCK_PATH,
    )
    assert raw == canonical_json_bytes(build.manifest)
    assert manifest == build.manifest
    assert artifact.content == build.artifact.content

    forged = deepcopy(manifest)
    forged["artifactSha256"] = "0" * 64
    forged_path = tmp_path / "forged.json"
    write_json(forged_path, forged)
    with pytest.raises(EvaluationError, match="EVAL_CANDIDATE_BUILD_MANIFEST_MISMATCH"):
        load_candidate_build_manifest(forged_path, snapshot, policy, DEPENDENCY_LOCK_PATH)

    forged_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(EvaluationError, match="EVAL_INVALID_CANDIDATE_BUILD_MANIFEST"):
        load_candidate_build_manifest(forged_path, snapshot, policy, DEPENDENCY_LOCK_PATH)

    forged_path.write_text("{", encoding="utf-8")
    with pytest.raises(EvaluationError, match="EVAL_INVALID_CANDIDATE_BUILD_MANIFEST"):
        load_candidate_build_manifest(forged_path, snapshot, policy, DEPENDENCY_LOCK_PATH)


def test_candidate_build_fails_closed_for_membership_policy_or_dependency(
    tmp_path: Path,
) -> None:
    snapshot, policy, _ = candidate_context()
    assignments = dict(snapshot.assignments)
    assignments[snapshot.samples_for("train")[0].sample_id] = "validation"
    incomplete = replace(snapshot, assignments=assignments)
    with pytest.raises(EvaluationError, match="EVAL_CANDIDATE_TRAINING_MEMBERSHIP_MISMATCH"):
        build_candidate(incomplete, policy, DEPENDENCY_LOCK_PATH)

    policy_value = deepcopy(policy.value)
    policy_value["pipelineVersion"] = "other"
    with pytest.raises(EvaluationError, match="EVAL_CANDIDATE_POLICY_MISMATCH"):
        build_candidate(
            snapshot,
            EvaluationPolicy(value=policy_value, sha256=policy.sha256),
            DEPENDENCY_LOCK_PATH,
        )

    with pytest.raises(EvaluationError, match="EVAL_CANDIDATE_DEPENDENCY_IDENTITY_MISSING"):
        build_candidate(snapshot, policy, DEPENDENCY_LOCK_PATH.with_name("missing.lock"))

    empty_lock = tmp_path / "uv.lock"
    empty_lock.write_bytes(b"")
    with pytest.raises(EvaluationError, match="EVAL_CANDIDATE_DEPENDENCY_IDENTITY_MISSING"):
        build_candidate(snapshot, policy, empty_lock)


def test_candidate_report_and_comparison_match_reviewed_evidence() -> None:
    snapshot, policy, build = candidate_context()
    first = candidate_report(snapshot, policy, build)
    second = candidate_report(snapshot, policy, build)
    assert canonical_json_bytes(first) == canonical_json_bytes(second)

    reviewed_report, reviewed_report_bytes = load_evaluation_report(
        CANDIDATE_REPORT_PATH,
        REPORT_SCHEMA_PATH,
        snapshot,
        policy,
        build.artifact.sha256,
        evaluation_role="candidate",
        model_name=MODEL_NAME,
        model_version=CANDIDATE_MODEL_VERSION,
    )
    assert reviewed_report == first
    assert reviewed_report_bytes == canonical_json_bytes(first)

    champion = champion_report(snapshot, policy)
    comparison = compare_candidate(
        champion,
        first,
        REPORT_SCHEMA_PATH,
        snapshot,
        policy,
        champion["artifactSha256"],
        build.artifact.sha256,
        candidate_model_name=MODEL_NAME,
        candidate_model_version=CANDIDATE_MODEL_VERSION,
    )
    reviewed_comparison, reviewed_comparison_bytes = load_candidate_comparison(
        CANDIDATE_COMPARISON_PATH,
        COMPARISON_SCHEMA_PATH,
        champion,
        first,
        REPORT_SCHEMA_PATH,
        snapshot,
        policy,
        champion["artifactSha256"],
        build.artifact.sha256,
        candidate_model_name=MODEL_NAME,
        candidate_model_version=CANDIDATE_MODEL_VERSION,
    )
    assert comparison["eligible"] is True
    assert comparison["regressions"] == {
        "macroF1": 0.0,
        "meanTrueLabelModelScore": 0.0,
        "perClassRecall": {"invoice": 0.0, "report": 0.0},
    }
    assert comparison == reviewed_comparison
    assert reviewed_comparison_bytes == canonical_json_bytes(comparison)


class DegradedCandidateClassifier:
    checksum = "d" * 64

    @staticmethod
    def classify(text: str) -> ClassificationResult:
        return ClassificationResult(
            classification="invoice",
            confidence=0.9,
            model_version=CANDIDATE_MODEL_VERSION,
        )


def test_degraded_candidate_is_rejected_without_changing_champion() -> None:
    snapshot, policy, _ = candidate_context()
    champion = champion_report(snapshot, policy)
    champion_checksum_before = CHAMPION_CHECKSUM_PATH.read_bytes()
    degraded = evaluate_model(
        snapshot,
        policy,
        cast(DocumentClassifier, DegradedCandidateClassifier()),
        evaluation_role="candidate",
        model_name=MODEL_NAME,
        model_version=CANDIDATE_MODEL_VERSION,
    )

    comparison = compare_candidate(
        champion,
        degraded,
        REPORT_SCHEMA_PATH,
        snapshot,
        policy,
        champion["artifactSha256"],
        DegradedCandidateClassifier.checksum,
        candidate_model_name=MODEL_NAME,
        candidate_model_version=CANDIDATE_MODEL_VERSION,
    )

    assert comparison["eligible"] is False
    assert comparison["rejectionReasons"] == [
        "EVAL_CANDIDATE_ABSOLUTE_GATES_FAILED",
        "EVAL_CANDIDATE_MACRO_F1_REGRESSION",
        "EVAL_CANDIDATE_MEAN_SCORE_REGRESSION",
        "EVAL_CANDIDATE_REPORT_RECALL_REGRESSION",
    ]
    assert CHAMPION_CHECKSUM_PATH.read_bytes() == champion_checksum_before


def test_comparison_rejects_corrupted_candidate_lineage() -> None:
    snapshot, policy, build = candidate_context()
    champion = champion_report(snapshot, policy)
    report = candidate_report(snapshot, policy, build)
    report["artifactSha256"] = "0" * 64
    unsigned = {key: value for key, value in report.items() if key != "reportSha256"}
    report["reportSha256"] = sha256_bytes(canonical_json_bytes(unsigned))

    with pytest.raises(EvaluationError, match="EVAL_REPORT_ARTIFACT_MISMATCH"):
        compare_candidate(
            champion,
            report,
            REPORT_SCHEMA_PATH,
            snapshot,
            policy,
            champion["artifactSha256"],
            build.artifact.sha256,
            candidate_model_name=MODEL_NAME,
            candidate_model_version=CANDIDATE_MODEL_VERSION,
        )


@pytest.mark.parametrize(
    ("mutation", "refresh_digest", "code"),
    [
        (lambda value: value.update(eligible=False), True, "EVAL_COMPARISON_MISMATCH"),
        (
            lambda value: value.update(comparisonSha256="0" * 64),
            False,
            "EVAL_COMPARISON_DIGEST_MISMATCH",
        ),
        (lambda value: value.pop("eligible"), False, "EVAL_COMPARISON_SCHEMA_VIOLATION"),
        (
            lambda value: value["regressions"].update(macroF1=float("nan")),
            False,
            "EVAL_NONFINITE_COMPARISON",
        ),
    ],
)
def test_comparison_mutations_fail_closed(
    mutation: Any,
    refresh_digest: bool,
    code: str,
) -> None:
    snapshot, policy, build = candidate_context()
    champion = champion_report(snapshot, policy)
    report = candidate_report(snapshot, policy, build)
    comparison = compare_candidate(
        champion,
        report,
        REPORT_SCHEMA_PATH,
        snapshot,
        policy,
        champion["artifactSha256"],
        build.artifact.sha256,
        candidate_model_name=MODEL_NAME,
        candidate_model_version=CANDIDATE_MODEL_VERSION,
    )
    mutation(comparison)
    if refresh_digest:
        unsigned = {key: value for key, value in comparison.items() if key != "comparisonSha256"}
        comparison["comparisonSha256"] = sha256_bytes(canonical_json_bytes(unsigned))

    with pytest.raises(EvaluationError, match=code):
        validate_candidate_comparison(
            comparison,
            COMPARISON_SCHEMA_PATH,
            champion,
            report,
            REPORT_SCHEMA_PATH,
            snapshot,
            policy,
            champion["artifactSha256"],
            build.artifact.sha256,
            candidate_model_name=MODEL_NAME,
            candidate_model_version=CANDIDATE_MODEL_VERSION,
        )


def test_invalid_comparison_schema_fails_closed(tmp_path: Path) -> None:
    snapshot, policy, build = candidate_context()
    champion = champion_report(snapshot, policy)
    report = candidate_report(snapshot, policy, build)
    comparison = compare_candidate(
        champion,
        report,
        REPORT_SCHEMA_PATH,
        snapshot,
        policy,
        champion["artifactSha256"],
        build.artifact.sha256,
        candidate_model_name=MODEL_NAME,
        candidate_model_version=CANDIDATE_MODEL_VERSION,
    )
    schema_path = tmp_path / "schema.json"
    write_json(schema_path, {"type": "unsupported"})

    with pytest.raises(EvaluationError, match="EVAL_INVALID_COMPARISON_SCHEMA"):
        validate_candidate_comparison(
            comparison,
            schema_path,
            champion,
            report,
            REPORT_SCHEMA_PATH,
            snapshot,
            policy,
            champion["artifactSha256"],
            build.artifact.sha256,
            candidate_model_name=MODEL_NAME,
            candidate_model_version=CANDIDATE_MODEL_VERSION,
        )
