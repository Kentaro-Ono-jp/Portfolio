from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from reactorfront_ml.evaluation import (
    canonical_json_bytes,
    evaluate_champion,
    load_champion_baseline,
    load_dataset_snapshot,
    load_evaluation_policy,
    validate_evaluation_report,
)
from reactorfront_ml.model import DocumentClassifier, generate_artifact

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EVALUATION_ROOT = REPOSITORY_ROOT / "apps" / "ml" / "evaluation"
SNAPSHOT_PATH = EVALUATION_ROOT / "corpus" / "v1" / "snapshot.json"
POLICY_PATH = EVALUATION_ROOT / "policy-v1.json"
SCHEMA_PATH = EVALUATION_ROOT / "evaluation-report-v1.schema.json"
BASELINE_PATH = EVALUATION_ROOT / "champion-baseline-v1.json"
TRAINING_DATA_PATH = REPOSITORY_ROOT / "apps" / "ml" / "data" / "training.json"
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

    proof = {
        "absoluteGatesPassed": baseline["absoluteGatesPassed"],
        "artifactSha256": expected_artifact_sha256,
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
