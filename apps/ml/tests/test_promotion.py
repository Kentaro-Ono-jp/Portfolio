from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

import reactorfront_ml.promotion as promotion
from reactorfront_ml.evaluation import canonical_json_bytes
from reactorfront_ml.promotion import (
    PROMOTION_SELECTION,
    ROLLBACK_SELECTION,
    PromotionError,
    load_promoted_model,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EVALUATION_ROOT = REPOSITORY_ROOT / "apps" / "ml" / "evaluation"
MANIFEST_PATH = EVALUATION_ROOT / "promoted-model-v1.json"
SCHEMA_PATH = EVALUATION_ROOT / "promoted-model-v1.schema.json"


def write_manifest(path: Path, value: object) -> None:
    path.write_bytes(canonical_json_bytes(value))


def load(path: Path = MANIFEST_PATH):
    return load_promoted_model(path, SCHEMA_PATH, repository_root=REPOSITORY_ROOT)


def manifest_value() -> dict[str, object]:
    value = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_promoted_candidate_is_canonical_reproducible_and_fully_bound() -> None:
    first = load()
    second = load()

    assert first.selection_type == PROMOTION_SELECTION
    assert first.model_version == "document-type-candidate-v1"
    assert first.artifact.sha256 == (
        "17006d0e045fdc42547ca0b0dd058eb67532e6967a1136156c51e4cb4c00de09"
    )
    assert first.evaluation_report["reportSha256"] == (
        "83493ba1053c6252651e64a9afdb424385eb527c1c2ca94cbc99ade0d610d861"
    )
    assert first.comparison["eligible"] is True
    assert first.artifact.content == second.artifact.content
    assert first.manifest == second.manifest
    assert first.manifest_sha256 == second.manifest_sha256


def test_same_manifest_path_can_select_the_previously_accepted_champion_for_rollback(
    tmp_path: Path,
) -> None:
    value = manifest_value()
    value.update(
        artifactSha256="82996b9d7a715ee8aee3b9b291cb9538346d84f5398c6b4448c1c79725e9c2ac",
        evaluationReportSha256=("1337d7bf0368799ebd2bc088cfda16544ca78c3ed77f96ba265a7d9b090a19b5"),
        modelVersion="document-type-v1",
        selectionType=ROLLBACK_SELECTION,
    )
    path = tmp_path / "rollback.json"
    write_manifest(path, value)

    selected = load(path)

    assert selected.selection_type == ROLLBACK_SELECTION
    assert selected.model_version == "document-type-v1"
    assert selected.artifact.sha256 == value["artifactSha256"]
    assert selected.evaluation_report["evaluationRole"] == "champion-baseline"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ({"artifactSha256": "0" * 64}, "PROMOTION_LINEAGE_MISMATCH"),
        ({"comparisonSha256": "0" * 64}, "PROMOTION_LINEAGE_MISMATCH"),
        ({"datasetSha256": "0" * 64}, "PROMOTION_LINEAGE_MISMATCH"),
        ({"datasetVersion": "other"}, "PROMOTION_LINEAGE_MISMATCH"),
        ({"evaluationPolicySha256": "0" * 64}, "PROMOTION_LINEAGE_MISMATCH"),
        ({"evaluationPolicyVersion": "other"}, "PROMOTION_LINEAGE_MISMATCH"),
        ({"evaluationReportSha256": "0" * 64}, "PROMOTION_LINEAGE_MISMATCH"),
        ({"modelVersion": "unreviewed-newest-v9"}, "PROMOTION_SELECTED_IDENTITY_MISMATCH"),
        ({"pipelineVersion": "other"}, "PROMOTION_LINEAGE_MISMATCH"),
        ({"preprocessingVersion": "other"}, "PROMOTION_LINEAGE_MISMATCH"),
    ],
)
def test_promotion_rejects_mutated_selected_identity_without_changing_the_manifest(
    tmp_path: Path,
    mutation: dict[str, object],
    code: str,
) -> None:
    before = MANIFEST_PATH.read_bytes()
    value = manifest_value()
    value.update(mutation)
    path = tmp_path / "mutated.json"
    write_manifest(path, value)

    with pytest.raises(PromotionError) as raised:
        load(path)

    assert raised.value.code == code
    assert MANIFEST_PATH.read_bytes() == before


def test_promotion_rejects_unknown_rollback_target(tmp_path: Path) -> None:
    value = manifest_value()
    value.update(
        artifactSha256="0" * 64,
        evaluationReportSha256="1" * 64,
        modelVersion="unknown-rollback-target",
        selectionType=ROLLBACK_SELECTION,
    )
    path = tmp_path / "unknown-rollback.json"
    write_manifest(path, value)

    with pytest.raises(PromotionError) as raised:
        load(path)

    assert raised.value.code == "PROMOTION_SELECTED_IDENTITY_MISMATCH"


def test_promotion_rejects_independently_ineligible_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = promotion.load_candidate_comparison

    def ineligible(*args: object, **kwargs: object):
        value, raw = original(*args, **kwargs)
        changed = deepcopy(value)
        changed["eligible"] = False
        return changed, raw

    monkeypatch.setattr(promotion, "load_candidate_comparison", ineligible)

    with pytest.raises(PromotionError) as raised:
        load()

    assert raised.value.code == "PROMOTION_CANDIDATE_INELIGIBLE"


def test_promotion_rejects_noncanonical_or_invalid_manifest(tmp_path: Path) -> None:
    value = manifest_value()
    compact = tmp_path / "compact.json"
    compact.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")
    with pytest.raises(PromotionError, match="PROMOTION_NONCANONICAL_MANIFEST"):
        load(compact)

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    with pytest.raises(PromotionError, match="PROMOTION_INVALID_JSON"):
        load(invalid)

    shape = tmp_path / "shape.json"
    shape.write_text("[]\n", encoding="utf-8")
    with pytest.raises(PromotionError, match="PROMOTION_INVALID_JSON_SHAPE"):
        load(shape)

    nonfinite = tmp_path / "nonfinite.json"
    nonfinite.write_text('{"schemaVersion": NaN}\n', encoding="utf-8")
    with pytest.raises(PromotionError, match="PROMOTION_NONCANONICAL_MANIFEST"):
        load(nonfinite)

    extra = tmp_path / "extra.json"
    value["unreviewedNewestArtifact"] = "ignored"
    write_manifest(extra, value)
    with pytest.raises(PromotionError, match="PROMOTION_SCHEMA_VIOLATION"):
        load(extra)


def test_promotion_rejects_evidence_path_escape(tmp_path: Path) -> None:
    value = manifest_value()
    evidence = dict(value["evidence"])
    evidence["candidateReportPath"] = "apps/ml/../../../candidate-report-v1.json"
    value["evidence"] = evidence
    path = tmp_path / "escape.json"
    write_manifest(path, value)

    with pytest.raises(PromotionError, match="PROMOTION_INVALID_EVIDENCE_PATH"):
        load(path)


def test_promotion_rejects_invalid_schema_or_missing_evidence(tmp_path: Path) -> None:
    missing_schema = tmp_path / "missing.schema.json"
    with pytest.raises(PromotionError, match="PROMOTION_INVALID_SCHEMA"):
        load_promoted_model(
            MANIFEST_PATH,
            missing_schema,
            repository_root=REPOSITORY_ROOT,
        )

    value = manifest_value()
    evidence = dict(value["evidence"])
    evidence["candidateReportPath"] = "apps/ml/evaluation/missing-report.json"
    value["evidence"] = evidence
    path = tmp_path / "missing-evidence.json"
    write_manifest(path, value)
    with pytest.raises(PromotionError, match="PROMOTION_EVIDENCE_INVALID"):
        load(path)
