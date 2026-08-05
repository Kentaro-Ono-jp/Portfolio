from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from reactorfront_ml.evaluation import (
    EvaluationError,
    load_dataset_snapshot,
    load_evaluation_policy,
    load_evaluation_report,
)


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


def load_runtime_model_evidence(
    report_path: Path,
    *,
    repository_root: Path,
    dataset_snapshot_path: Path,
    evaluation_policy_path: Path,
    evaluation_report_schema_path: Path,
    expected_model_version: str,
    expected_artifact_sha256: str,
) -> RuntimeModelEvidence:
    try:
        snapshot = load_dataset_snapshot(repository_root, dataset_snapshot_path)
        policy = load_evaluation_policy(evaluation_policy_path)
        value, _ = load_evaluation_report(
            report_path,
            evaluation_report_schema_path,
            snapshot,
            policy,
            expected_artifact_sha256,
            evaluation_role="champion-baseline",
            model_name="reactorfront-document-type",
            model_version=expected_model_version,
        )
    except EvaluationError as error:
        raise RuntimeLineageError(
            f"Champion evaluation lineage is invalid: {error.code}"
        ) from error

    if value["absoluteGatesPassed"] is not True:
        raise RuntimeLineageError("Runtime lineage requires an accepted champion baseline")

    return RuntimeModelEvidence(
        dataset_version=value["datasetVersion"],
        dataset_sha256=value["datasetSha256"],
        preprocessing_version=value["preprocessingVersion"],
        pipeline_version=value["pipelineVersion"],
        artifact_sha256=value["artifactSha256"],
        evaluation_policy_version=value["policyVersion"],
        evaluation_policy_sha256=value["policySha256"],
        evaluation_report_sha256=value["reportSha256"],
    )
