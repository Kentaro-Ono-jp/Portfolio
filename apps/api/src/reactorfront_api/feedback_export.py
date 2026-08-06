from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol, cast

from reactorfront_api.domain import MeasuredModelEvidence

EXPORT_SCHEMA_VERSION = 1
INVENTORY_SCHEMA_VERSION = 1
SUPPORTED_CLASSIFICATIONS = frozenset({"invoice", "report"})
SUPPORTED_LICENSE = "MIT"
SUPPORTED_PROVENANCE = "repository-owned-synthetic"
SOURCE_PATH_PREFIX = "apps/ml/evaluation/corpus/"
OMISSION_ORDER = (
    "not-completed",
    "nonterminal-review",
    "invalid-source-identity",
    "unsupported-or-inconsistent-label",
    "legacy-unmeasured",
    "incomplete-lineage",
    "unknown-source",
    "duplicate-observation",
    "conflicting-observation",
)


class FeedbackExportError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class FeedbackObservation:
    source_sha256: str
    processing_status: str
    machine_classification: str | None
    final_classification: str | None
    review_outcome: str | None
    model_version: str | None
    model_evidence: MeasuredModelEvidence | None


class FeedbackObservationRepository(Protocol):
    def list_feedback_observations(self) -> tuple[FeedbackObservation, ...]: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class CorpusInventory:
    source_sha256s: frozenset[str]
    inventory_sha256: str


def canonical_json_bytes(value: object) -> bytes:
    try:
        rendered = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise FeedbackExportError("FEEDBACK_NONCANONICAL_VALUE") from error
    return f"{rendered}\n".encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_corpus_inventory(path: Path) -> CorpusInventory:
    try:
        raw = path.read_bytes()
        parsed = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FeedbackExportError("FEEDBACK_INVALID_INVENTORY_JSON") from error
    if not isinstance(parsed, dict):
        raise FeedbackExportError("FEEDBACK_INVALID_INVENTORY")
    value = cast(dict[str, Any], parsed)
    if raw != canonical_json_bytes(value):
        raise FeedbackExportError("FEEDBACK_NONCANONICAL_INVENTORY")
    if set(value) != {"description", "provenanceClasses", "samples", "schemaVersion"}:
        raise FeedbackExportError("FEEDBACK_INVALID_INVENTORY")
    if (
        value["schemaVersion"] != INVENTORY_SCHEMA_VERSION
        or value["provenanceClasses"] != [SUPPORTED_PROVENANCE]
        or not _is_required_string(value["description"])
        or not isinstance(value["samples"], list)
        or not value["samples"]
    ):
        raise FeedbackExportError("FEEDBACK_INVALID_INVENTORY")

    sample_ids: set[str] = set()
    source_sha256s: set[str] = set()
    ordered_sample_ids: list[str] = []
    for raw_sample in value["samples"]:
        if not isinstance(raw_sample, dict):
            raise FeedbackExportError("FEEDBACK_INVALID_INVENTORY_SAMPLE")
        sample = cast(dict[str, Any], raw_sample)
        if set(sample) != {
            "familyId",
            "label",
            "license",
            "path",
            "provenance",
            "sampleId",
            "sourceSha256",
        }:
            raise FeedbackExportError("FEEDBACK_INVALID_INVENTORY_SAMPLE")
        sample_id = sample["sampleId"]
        if not _is_required_string(sample_id) or sample_id in sample_ids:
            raise FeedbackExportError("FEEDBACK_INVALID_INVENTORY_SAMPLE")
        sample_ids.add(sample_id)
        ordered_sample_ids.append(sample_id)
        if (
            sample["label"] not in SUPPORTED_CLASSIFICATIONS
            or sample["provenance"] != SUPPORTED_PROVENANCE
            or sample["license"] != SUPPORTED_LICENSE
            or not _is_required_string(sample["familyId"])
            or not _is_portable_source_path(sample["path"])
            or not _is_sha256(sample["sourceSha256"])
        ):
            raise FeedbackExportError("FEEDBACK_INVALID_INVENTORY_SAMPLE")
        source_sha256 = cast(str, sample["sourceSha256"])
        if source_sha256 in source_sha256s:
            raise FeedbackExportError("FEEDBACK_CONFLICTING_INVENTORY")
        source_sha256s.add(source_sha256)
    if ordered_sample_ids != sorted(ordered_sample_ids):
        raise FeedbackExportError("FEEDBACK_NONCANONICAL_INVENTORY")
    return CorpusInventory(
        source_sha256s=frozenset(source_sha256s),
        inventory_sha256=sha256_bytes(raw),
    )


class FeedbackExporter:
    def __init__(
        self,
        *,
        repository: FeedbackObservationRepository,
        inventory_path: Path,
    ) -> None:
        self._repository = repository
        self._inventory_path = inventory_path

    def export_bytes(self) -> bytes:
        inventory = load_corpus_inventory(self._inventory_path)
        try:
            observations = self._repository.list_feedback_observations()
        except Exception as error:
            raise FeedbackExportError("FEEDBACK_DATABASE_UNAVAILABLE") from error
        candidates, omission_counts = _project_candidates(observations, inventory)
        unsigned: dict[str, object] = {
            "candidates": candidates,
            "inventorySha256": inventory.inventory_sha256,
            "omissions": [
                {"count": omission_counts[reason], "reason": reason}
                for reason in OMISSION_ORDER
                if omission_counts.get(reason, 0) > 0
            ],
            "schemaVersion": EXPORT_SCHEMA_VERSION,
        }
        document = {
            **unsigned,
            "exportSha256": sha256_bytes(canonical_json_bytes(unsigned)),
        }
        return canonical_json_bytes(document)


def _project_candidates(
    observations: tuple[FeedbackObservation, ...],
    inventory: CorpusInventory,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    omission_counts: dict[str, int] = {}
    by_source: dict[str, list[dict[str, object]]] = {}
    for observation in observations:
        reason = _observation_omission_reason(observation, inventory)
        if reason is not None:
            omission_counts[reason] = omission_counts.get(reason, 0) + 1
            continue
        candidate = _candidate_without_identity(observation)
        by_source.setdefault(observation.source_sha256, []).append(candidate)

    candidates: list[dict[str, object]] = []
    for source_sha256 in sorted(by_source):
        source_candidates = by_source[source_sha256]
        distinct = {canonical_json_bytes(candidate): candidate for candidate in source_candidates}
        if len(distinct) != 1:
            omission_counts["conflicting-observation"] = omission_counts.get(
                "conflicting-observation", 0
            ) + len(source_candidates)
            continue
        candidate = next(iter(distinct.values()))
        duplicates = len(source_candidates) - 1
        if duplicates:
            omission_counts["duplicate-observation"] = (
                omission_counts.get("duplicate-observation", 0) + duplicates
            )
        candidates.append(
            {
                "candidateId": sha256_bytes(canonical_json_bytes(candidate)),
                **candidate,
            }
        )
    candidates.sort(key=lambda candidate: cast(str, candidate["candidateId"]))
    return candidates, omission_counts


def _observation_omission_reason(
    observation: FeedbackObservation,
    inventory: CorpusInventory,
) -> str | None:
    if observation.processing_status != "completed":
        return "not-completed"
    if observation.review_outcome not in {"approved", "corrected"}:
        return "nonterminal-review"
    if not _is_sha256(observation.source_sha256):
        return "invalid-source-identity"
    if (
        observation.machine_classification not in SUPPORTED_CLASSIFICATIONS
        or observation.final_classification not in SUPPORTED_CLASSIFICATIONS
        or (
            observation.review_outcome == "approved"
            and observation.machine_classification != observation.final_classification
        )
        or (
            observation.review_outcome == "corrected"
            and observation.machine_classification == observation.final_classification
        )
    ):
        return "unsupported-or-inconsistent-label"
    if observation.model_evidence is None:
        return "legacy-unmeasured"
    if not _has_complete_lineage(observation.model_version, observation.model_evidence):
        return "incomplete-lineage"
    if observation.source_sha256 not in inventory.source_sha256s:
        return "unknown-source"
    return None


def _candidate_without_identity(observation: FeedbackObservation) -> dict[str, object]:
    evidence = observation.model_evidence
    if evidence is None or observation.model_version is None:
        raise FeedbackExportError("FEEDBACK_INTERNAL_INVARIANT")
    return {
        "finalClassification": observation.final_classification,
        "machineClassification": observation.machine_classification,
        "modelLineage": {
            "artifactSha256": evidence.artifact_sha256,
            "datasetSha256": evidence.dataset_sha256,
            "datasetVersion": evidence.dataset_version,
            "evaluationPolicySha256": evidence.evaluation_policy_sha256,
            "evaluationPolicyVersion": evidence.evaluation_policy_version,
            "evaluationReportSha256": evidence.evaluation_report_sha256,
            "modelVersion": observation.model_version,
            "pipelineVersion": evidence.pipeline_version,
            "preprocessingVersion": evidence.preprocessing_version,
        },
        "reviewOutcome": observation.review_outcome,
        "sourceSha256": observation.source_sha256,
    }


def _has_complete_lineage(
    model_version: str | None,
    evidence: MeasuredModelEvidence,
) -> bool:
    versions = (
        model_version,
        evidence.dataset_version,
        evidence.preprocessing_version,
        evidence.pipeline_version,
        evidence.evaluation_policy_version,
    )
    digests = (
        evidence.dataset_sha256,
        evidence.artifact_sha256,
        evidence.evaluation_policy_sha256,
        evidence.evaluation_report_sha256,
    )
    return all(_is_required_string(value) for value in versions) and all(
        _is_sha256(value) for value in digests
    )


def _is_required_string(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_portable_source_path(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith(SOURCE_PATH_PREFIX) or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and path.as_posix() == value
