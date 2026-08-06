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
        "83493ba1053c6252651e64a9afdb424385eb527c1c2ca94cbc99ade0d610d861"
    )


@pytest.mark.parametrize(
    ("model_version", "artifact_sha256"),
    [
        (
            "unreviewed-newest-v9",
            "17006d0e045fdc42547ca0b0dd058eb67532e6967a1136156c51e4cb4c00de09",
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
