from __future__ import annotations

from dataclasses import dataclass

from reactorfront_ml.promotion import PromotedModel


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
    promoted: PromotedModel,
    *,
    expected_model_version: str,
    expected_artifact_sha256: str,
) -> RuntimeModelEvidence:
    value = promoted.evaluation_report
    if (
        promoted.model_version != expected_model_version
        or promoted.artifact.sha256 != expected_artifact_sha256
        or value.get("modelVersion") != expected_model_version
        or value.get("artifactSha256") != expected_artifact_sha256
        or value.get("absoluteGatesPassed") is not True
    ):
        raise RuntimeLineageError("Runtime lineage does not match the promoted model")

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
