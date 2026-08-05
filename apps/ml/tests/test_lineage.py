from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from reactorfront_ml.lineage import RuntimeLineageError, load_runtime_model_evidence

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
REPORT_PATH = REPOSITORY_ROOT / "apps/ml/evaluation/champion-baseline-v1.json"
ARTIFACT_SHA256 = "82996b9d7a715ee8aee3b9b291cb9538346d84f5398c6b4448c1c79725e9c2ac"


def test_load_runtime_model_evidence_binds_the_accepted_champion() -> None:
    evidence = load_runtime_model_evidence(
        REPORT_PATH,
        expected_model_version="document-type-v1",
        expected_artifact_sha256=ARTIFACT_SHA256,
    )

    assert evidence.dataset_version == "reactorfront-synthetic-documents-v1"
    assert evidence.artifact_sha256 == ARTIFACT_SHA256
    assert evidence.evaluation_report_sha256 == (
        "1337d7bf0368799ebd2bc088cfda16544ca78c3ed77f96ba265a7d9b090a19b5"
    )


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ({"modelVersion": "document-type-candidate-v1"}, "model version"),
        ({"artifactSha256": "0" * 64}, "artifact digest"),
        ({"absoluteGatesPassed": False}, "accepted champion"),
    ],
)
def test_load_runtime_model_evidence_rejects_mutated_champion(
    tmp_path: Path,
    mutation: dict[str, object],
    expected: str,
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

    with pytest.raises(RuntimeLineageError, match=expected):
        load_runtime_model_evidence(
            path,
            expected_model_version="document-type-v1",
            expected_artifact_sha256=ARTIFACT_SHA256,
        )


def test_load_runtime_model_evidence_rejects_noncanonical_report(tmp_path: Path) -> None:
    value = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    path = tmp_path / "pretty.json"
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(RuntimeLineageError, match="not canonical"):
        load_runtime_model_evidence(
            path,
            expected_model_version="document-type-v1",
            expected_artifact_sha256=ARTIFACT_SHA256,
        )
