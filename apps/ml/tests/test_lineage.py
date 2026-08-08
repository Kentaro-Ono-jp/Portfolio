from __future__ import annotations

from pathlib import Path

import pytest

from reactorfront_ml.lineage import RuntimeLineageError, load_runtime_model_evidence
from reactorfront_ml.promotion import load_promoted_model

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EVALUATION_ROOT = REPOSITORY_ROOT / "apps" / "ml" / "evaluation"


def promoted():
    return load_promoted_model(
        EVALUATION_ROOT / "promoted-model-v1.json",
        EVALUATION_ROOT / "promoted-model-v1.schema.json",
        repository_root=REPOSITORY_ROOT,
    )


def test_runtime_model_evidence_binds_the_promoted_candidate() -> None:
    selected = promoted()
    evidence = load_runtime_model_evidence(
        selected,
        expected_model_version=selected.model_version,
        expected_artifact_sha256=selected.artifact.sha256,
    )

    assert evidence.dataset_version == "reactorfront-synthetic-documents-v1"
    assert evidence.artifact_sha256 == selected.artifact.sha256
    assert evidence.evaluation_report_sha256 == (
        "4562e0cda501400a8e1988bb0463bac4b9c12537da9b985ebe31e0c897e4fa18"
    )


@pytest.mark.parametrize(
    ("model_version", "artifact_sha256"),
    [
        (
            "unreviewed-newest-v9",
            "970723c2d4a11cce2567f931e55cc4f673dc0f359a9d0e0e8730136dc661e9ae",
        ),
        ("document-type-candidate-v1", "0" * 64),
    ],
)
def test_runtime_model_evidence_rejects_artifact_or_version_mismatch(
    model_version: str,
    artifact_sha256: str,
) -> None:
    with pytest.raises(RuntimeLineageError):
        load_runtime_model_evidence(
            promoted(),
            expected_model_version=model_version,
            expected_artifact_sha256=artifact_sha256,
        )
