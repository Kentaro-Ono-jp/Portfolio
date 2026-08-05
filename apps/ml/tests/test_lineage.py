from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from reactorfront_ml.lineage import (
    RuntimeLineageError,
    RuntimeModelEvidence,
    load_runtime_model_evidence,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EVALUATION_ROOT = REPOSITORY_ROOT / "apps/ml/evaluation"
REPORT_PATH = EVALUATION_ROOT / "champion-baseline-v1.json"
SNAPSHOT_PATH = EVALUATION_ROOT / "corpus/v1/snapshot.json"
POLICY_PATH = EVALUATION_ROOT / "policy-v1.json"
SCHEMA_PATH = EVALUATION_ROOT / "evaluation-report-v1.schema.json"
ARTIFACT_SHA256 = "82996b9d7a715ee8aee3b9b291cb9538346d84f5398c6b4448c1c79725e9c2ac"


def load(path: Path) -> RuntimeModelEvidence:
    return load_runtime_model_evidence(
        path,
        repository_root=REPOSITORY_ROOT,
        dataset_snapshot_path=SNAPSHOT_PATH,
        evaluation_policy_path=POLICY_PATH,
        evaluation_report_schema_path=SCHEMA_PATH,
        expected_model_version="document-type-v1",
        expected_artifact_sha256=ARTIFACT_SHA256,
    )


def test_load_runtime_model_evidence_binds_the_accepted_champion() -> None:
    evidence = load(REPORT_PATH)

    assert evidence.dataset_version == "reactorfront-synthetic-documents-v1"
    assert evidence.artifact_sha256 == ARTIFACT_SHA256
    assert evidence.evaluation_report_sha256 == (
        "1337d7bf0368799ebd2bc088cfda16544ca78c3ed77f96ba265a7d9b090a19b5"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        {"corpusSha256": "0" * 64},
        {"datasetSha256": "0" * 64},
        {"datasetVersion": "forged-dataset-v1"},
        {"evaluationRole": "candidate"},
        {"modelName": "forged-model"},
        {"modelVersion": "document-type-candidate-v1"},
        {"pipelineVersion": "forged-pipeline-v1"},
        {"policySha256": "0" * 64},
        {"policyVersion": "forged-policy-v1"},
        {"preprocessingVersion": "forged-preprocessing-v1"},
        {"splitSha256": "0" * 64},
        {
            "testSampleIds": list(
                reversed(
                    [
                        "invoice-test-001",
                        "invoice-test-002",
                        "report-test-001",
                        "report-test-002",
                    ]
                )
            )
        },
        {"totalSampleCount": 5},
        {"artifactSha256": "0" * 64},
        {"absoluteGatesPassed": False},
    ],
)
def test_load_runtime_model_evidence_rejects_coherent_lineage_mutation(
    tmp_path: Path,
    mutation: dict[str, object],
) -> None:
    value = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    value.update(mutation)
    unsigned = {key: selected for key, selected in value.items() if key != "reportSha256"}
    canonical_unsigned = (
        json.dumps(unsigned, allow_nan=False, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    value["reportSha256"] = hashlib.sha256(canonical_unsigned).hexdigest()
    path = tmp_path / "mutated.json"
    path.write_bytes(
        (
            json.dumps(value, allow_nan=False, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
    )

    with pytest.raises(RuntimeLineageError):
        load(path)


def test_load_runtime_model_evidence_rejects_noncanonical_report(tmp_path: Path) -> None:
    value = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    path = tmp_path / "compact.json"
    path.write_bytes(json.dumps(value, separators=(",", ":"), sort_keys=True).encode())

    with pytest.raises(RuntimeLineageError):
        load(path)


@pytest.mark.parametrize("content", ["{", '{"reportSha256": NaN}\n'])
def test_load_runtime_model_evidence_rejects_unavailable_json(
    tmp_path: Path,
    content: str,
) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(RuntimeLineageError):
        load(path)


def test_load_runtime_model_evidence_rejects_missing_report(tmp_path: Path) -> None:
    with pytest.raises(RuntimeLineageError):
        load(tmp_path / "missing.json")


def test_load_runtime_model_evidence_rejects_report_digest_mismatch(tmp_path: Path) -> None:
    value = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    value["reportSha256"] = "0" * 64
    path = tmp_path / "digest-mismatch.json"
    path.write_bytes(
        (
            json.dumps(value, allow_nan=False, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
        ).encode()
    )

    with pytest.raises(RuntimeLineageError):
        load(path)
