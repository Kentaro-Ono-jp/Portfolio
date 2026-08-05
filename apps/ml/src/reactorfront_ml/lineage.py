from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


class RuntimeLineageError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class RuntimeModelEvidence:
    dataset_version: str
    dataset_sha256: str
    preprocessing_version: str
    pipeline_version: str
    artifact_sha256: str
    evaluation_policy_version: str
    evaluation_policy_sha256: str
    evaluation_report_sha256: str

    def to_event_payload(self) -> dict[str, str]:
        return {
            "status": "measured",
            "datasetVersion": self.dataset_version,
            "datasetSha256": self.dataset_sha256,
            "preprocessingVersion": self.preprocessing_version,
            "pipelineVersion": self.pipeline_version,
            "artifactSha256": self.artifact_sha256,
            "evaluationPolicyVersion": self.evaluation_policy_version,
            "evaluationPolicySha256": self.evaluation_policy_sha256,
            "evaluationReportSha256": self.evaluation_report_sha256,
        }


def _canonical_json_bytes(value: object) -> bytes:
    try:
        rendered = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise RuntimeLineageError("Champion evaluation report is not canonical") from error
    return f"{rendered}\n".encode()


def _required_string(value: dict[str, object], key: str) -> str:
    selected = value.get(key)
    if not isinstance(selected, str) or not selected or len(selected) > 128:
        raise RuntimeLineageError(f"Champion lineage field {key} is invalid")
    return selected


def _required_sha256(value: dict[str, object], key: str) -> str:
    selected = _required_string(value, key)
    if len(selected) != 64 or any(character not in "0123456789abcdef" for character in selected):
        raise RuntimeLineageError(f"Champion lineage digest {key} is invalid")
    return selected


def load_runtime_model_evidence(
    report_path: Path,
    *,
    expected_model_version: str,
    expected_artifact_sha256: str,
) -> RuntimeModelEvidence:
    try:
        raw = report_path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeLineageError("Champion evaluation report is unavailable") from error
    if not isinstance(value, dict) or raw != _canonical_json_bytes(value):
        raise RuntimeLineageError("Champion evaluation report is not canonical")

    report_sha256 = _required_sha256(value, "reportSha256")
    unsigned = {key: selected for key, selected in value.items() if key != "reportSha256"}
    if hashlib.sha256(_canonical_json_bytes(unsigned)).hexdigest() != report_sha256:
        raise RuntimeLineageError("Champion evaluation report digest does not match")
    if (
        value.get("evaluationRole") != "champion-baseline"
        or value.get("absoluteGatesPassed") is not True
    ):
        raise RuntimeLineageError("Runtime lineage requires an accepted champion baseline")
    if _required_string(value, "modelVersion") != expected_model_version:
        raise RuntimeLineageError("Champion model version does not match the runtime")
    artifact_sha256 = _required_sha256(value, "artifactSha256")
    if artifact_sha256 != expected_artifact_sha256:
        raise RuntimeLineageError("Champion artifact digest does not match the runtime")

    return RuntimeModelEvidence(
        dataset_version=_required_string(value, "datasetVersion"),
        dataset_sha256=_required_sha256(value, "datasetSha256"),
        preprocessing_version=_required_string(value, "preprocessingVersion"),
        pipeline_version=_required_string(value, "pipelineVersion"),
        artifact_sha256=artifact_sha256,
        evaluation_policy_version=_required_string(value, "policyVersion"),
        evaluation_policy_sha256=_required_sha256(value, "policySha256"),
        evaluation_report_sha256=report_sha256,
    )
