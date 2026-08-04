from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from reactorfront_ml.candidate import (
    CANDIDATE_MODEL_VERSION,
    build_candidate,
    load_candidate_build_manifest,
)
from reactorfront_ml.evaluation import (
    EvaluationError,
    canonical_json_bytes,
    compare_candidate,
    evaluate_champion,
    evaluate_model,
    load_candidate_comparison,
    load_champion_baseline,
    load_dataset_snapshot,
    load_evaluation_policy,
    load_evaluation_report,
    sha256_bytes,
    validate_candidate_comparison,
    validate_evaluation_report,
)
from reactorfront_ml.model import MODEL_NAME, DocumentClassifier, generate_artifact

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EVALUATION_ROOT = REPOSITORY_ROOT / "apps" / "ml" / "evaluation"
SNAPSHOT_PATH = EVALUATION_ROOT / "corpus" / "v1" / "snapshot.json"
POLICY_PATH = EVALUATION_ROOT / "policy-v1.json"
SCHEMA_PATH = EVALUATION_ROOT / "evaluation-report-v1.schema.json"
COMPARISON_SCHEMA_PATH = EVALUATION_ROOT / "candidate-comparison-v1.schema.json"
BASELINE_PATH = EVALUATION_ROOT / "champion-baseline-v1.json"
CANDIDATE_BUILD_PATH = EVALUATION_ROOT / "candidate-build-v1.json"
CANDIDATE_REPORT_PATH = EVALUATION_ROOT / "candidate-report-v1.json"
CANDIDATE_COMPARISON_PATH = EVALUATION_ROOT / "candidate-comparison-v1.json"
TRAINING_DATA_PATH = REPOSITORY_ROOT / "apps" / "ml" / "data" / "training.json"
DEPENDENCY_LOCK_PATH = REPOSITORY_ROOT / "apps" / "ml" / "uv.lock"
EXPECTED_CHECKSUM_PATH = REPOSITORY_ROOT / "apps" / "ml" / "model.expected.sha256"
PROOF_PATH = REPOSITORY_ROOT / "artifacts" / "verification" / "ml-evaluation-proof.json"


def main() -> int:
    snapshot = load_dataset_snapshot(REPOSITORY_ROOT, SNAPSHOT_PATH)
    policy = load_evaluation_policy(POLICY_PATH)
    training_document = json.loads(TRAINING_DATA_PATH.read_text(encoding="utf-8"))
    training_examples = sorted(
        (example["label"], example["text"]) for example in training_document["examples"]
    )
    snapshot_training = sorted(
        (sample.label, sample.text) for sample in snapshot.samples_for("train")
    )
    if training_examples != snapshot_training:
        raise RuntimeError(
            "Snapshot training split differs from the champion training data"
        )
    expected_artifact_sha256 = EXPECTED_CHECKSUM_PATH.read_text(
        encoding="utf-8"
    ).strip()
    first_artifact = generate_artifact(TRAINING_DATA_PATH)
    second_artifact = generate_artifact(TRAINING_DATA_PATH)
    if first_artifact.content != second_artifact.content:
        raise RuntimeError("Champion artifact reconstruction drifted")
    if first_artifact.sha256 != expected_artifact_sha256:
        raise RuntimeError("Champion artifact does not match the reviewed checksum")

    with TemporaryDirectory(prefix="reactorfront-champion-evaluation-") as directory:
        root = Path(directory)
        artifact_path = root / "model.json"
        checksum_path = root / "model.sha256"
        artifact_path.write_bytes(first_artifact.content)
        checksum_path.write_text(f"{first_artifact.sha256}\n", encoding="utf-8")
        classifier = DocumentClassifier(
            artifact_path=artifact_path,
            checksum_path=checksum_path,
        )
        first_report = evaluate_champion(snapshot, policy, classifier)
        second_report = evaluate_champion(snapshot, policy, classifier)

    validate_evaluation_report(
        first_report,
        SCHEMA_PATH,
        snapshot,
        policy,
        expected_artifact_sha256,
    )
    if canonical_json_bytes(first_report) != canonical_json_bytes(second_report):
        raise RuntimeError("Champion report reconstruction drifted")
    baseline, baseline_bytes = load_champion_baseline(
        BASELINE_PATH,
        SCHEMA_PATH,
        snapshot,
        policy,
        expected_artifact_sha256,
    )
    if canonical_json_bytes(first_report) != baseline_bytes:
        raise RuntimeError("Champion report differs from the reviewed baseline")

    first_candidate_build = build_candidate(snapshot, policy, DEPENDENCY_LOCK_PATH)
    second_candidate_build = build_candidate(snapshot, policy, DEPENDENCY_LOCK_PATH)
    if (
        first_candidate_build.artifact.content
        != second_candidate_build.artifact.content
        or first_candidate_build.artifact.sha256
        != second_candidate_build.artifact.sha256
        or first_candidate_build.manifest != second_candidate_build.manifest
    ):
        raise RuntimeError("Candidate artifact reconstruction drifted")
    reviewed_build, reviewed_build_bytes, reviewed_artifact = (
        load_candidate_build_manifest(
            CANDIDATE_BUILD_PATH,
            snapshot,
            policy,
            DEPENDENCY_LOCK_PATH,
        )
    )
    if (
        canonical_json_bytes(first_candidate_build.manifest) != reviewed_build_bytes
        or first_candidate_build.artifact.content != reviewed_artifact.content
        or first_candidate_build.manifest != reviewed_build
    ):
        raise RuntimeError("Candidate build differs from the reviewed identity")

    with TemporaryDirectory(prefix="reactorfront-candidate-evaluation-") as directory:
        root = Path(directory)
        artifact_path = root / "model.json"
        checksum_path = root / "model.sha256"
        artifact_path.write_bytes(first_candidate_build.artifact.content)
        checksum_path.write_text(
            f"{first_candidate_build.artifact.sha256}\n", encoding="utf-8"
        )
        candidate_classifier = DocumentClassifier(
            artifact_path=artifact_path,
            checksum_path=checksum_path,
            expected_model_version=CANDIDATE_MODEL_VERSION,
        )
        first_candidate_report = evaluate_model(
            snapshot,
            policy,
            candidate_classifier,
            evaluation_role="candidate",
            model_name=MODEL_NAME,
            model_version=CANDIDATE_MODEL_VERSION,
        )
        second_candidate_report = evaluate_model(
            snapshot,
            policy,
            candidate_classifier,
            evaluation_role="candidate",
            model_name=MODEL_NAME,
            model_version=CANDIDATE_MODEL_VERSION,
        )
    if canonical_json_bytes(first_candidate_report) != canonical_json_bytes(
        second_candidate_report
    ):
        raise RuntimeError("Candidate report reconstruction drifted")
    reviewed_candidate_report, reviewed_candidate_bytes = load_evaluation_report(
        CANDIDATE_REPORT_PATH,
        SCHEMA_PATH,
        snapshot,
        policy,
        first_candidate_build.artifact.sha256,
        evaluation_role="candidate",
        model_name=MODEL_NAME,
        model_version=CANDIDATE_MODEL_VERSION,
    )
    if canonical_json_bytes(first_candidate_report) != reviewed_candidate_bytes:
        raise RuntimeError("Candidate report differs from the reviewed evidence")

    comparison = compare_candidate(
        baseline,
        first_candidate_report,
        SCHEMA_PATH,
        snapshot,
        policy,
        expected_artifact_sha256,
        first_candidate_build.artifact.sha256,
        candidate_model_name=MODEL_NAME,
        candidate_model_version=CANDIDATE_MODEL_VERSION,
    )
    validate_candidate_comparison(
        comparison,
        COMPARISON_SCHEMA_PATH,
        baseline,
        first_candidate_report,
        SCHEMA_PATH,
        snapshot,
        policy,
        expected_artifact_sha256,
        first_candidate_build.artifact.sha256,
        candidate_model_name=MODEL_NAME,
        candidate_model_version=CANDIDATE_MODEL_VERSION,
    )
    reviewed_comparison, reviewed_comparison_bytes = load_candidate_comparison(
        CANDIDATE_COMPARISON_PATH,
        COMPARISON_SCHEMA_PATH,
        baseline,
        reviewed_candidate_report,
        SCHEMA_PATH,
        snapshot,
        policy,
        expected_artifact_sha256,
        first_candidate_build.artifact.sha256,
        candidate_model_name=MODEL_NAME,
        candidate_model_version=CANDIDATE_MODEL_VERSION,
    )
    if (
        comparison != reviewed_comparison
        or canonical_json_bytes(comparison) != reviewed_comparison_bytes
    ):
        raise RuntimeError("Candidate comparison differs from the reviewed decision")
    if comparison["eligible"] is not True:
        raise RuntimeError("Reviewed candidate is not promotion eligible")

    corrupted_report = deepcopy(first_candidate_report)
    corrupted_report["artifactSha256"] = "0" * 64
    unsigned = {
        key: value for key, value in corrupted_report.items() if key != "reportSha256"
    }
    corrupted_report["reportSha256"] = sha256_bytes(canonical_json_bytes(unsigned))
    rejection_code = ""
    try:
        compare_candidate(
            baseline,
            corrupted_report,
            SCHEMA_PATH,
            snapshot,
            policy,
            expected_artifact_sha256,
            first_candidate_build.artifact.sha256,
            candidate_model_name=MODEL_NAME,
            candidate_model_version=CANDIDATE_MODEL_VERSION,
        )
    except EvaluationError as error:
        rejection_code = error.code
    if rejection_code != "EVAL_REPORT_ARTIFACT_MISMATCH":
        raise RuntimeError(
            "Corrupted candidate lineage was not rejected deterministically"
        )
    if (
        EXPECTED_CHECKSUM_PATH.read_text(encoding="utf-8").strip()
        != expected_artifact_sha256
    ):
        raise RuntimeError("Candidate evaluation changed the champion identity")

    proof = {
        "absoluteGatesPassed": baseline["absoluteGatesPassed"],
        "artifactSha256": expected_artifact_sha256,
        "candidateArtifactSha256": first_candidate_build.artifact.sha256,
        "candidateEligible": comparison["eligible"],
        "candidateReportSha256": first_candidate_report["reportSha256"],
        "comparisonSha256": comparison["comparisonSha256"],
        "corruptedCandidateRejectionCode": rejection_code,
        "datasetSha256": snapshot.dataset_sha256,
        "macroF1": baseline["metrics"]["macroF1"],
        "meanTrueLabelModelScore": baseline["metrics"]["meanTrueLabelModelScore"],
        "processedSampleCount": baseline["processedSampleCount"],
        "reportSha256": baseline["reportSha256"],
        "splitSha256": snapshot.split_sha256,
    }
    PROOF_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROOF_PATH.write_text(
        json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(proof, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
