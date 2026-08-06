from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass, replace
from io import BytesIO, StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from scripts.pdf_fixture import build_fixture

import reactorfront_api.feedback_export_main as feedback_export_main
from reactorfront_api.domain import MeasuredModelEvidence
from reactorfront_api.feedback_export import (
    FeedbackExporter,
    FeedbackExportError,
    FeedbackObservation,
    canonical_json_bytes,
    load_feedback_inventory,
    sha256_bytes,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
INVENTORY_PATH = REPOSITORY_ROOT / "apps/api/feedback/feedback-source-inventory-v1.json"
CORPUS_INVENTORY_PATH = REPOSITORY_ROOT / "apps/ml/evaluation/corpus/v1/corpus.json"
FIXTURE_GENERATOR_PATH = REPOSITORY_ROOT / "scripts/pdf_fixture.py"
SCHEMA_PATH = REPOSITORY_ROOT / "apps/api/feedback/feedback-candidate-export-v1.schema.json"
MEASURED_EVIDENCE = MeasuredModelEvidence(
    dataset_version="reactorfront-synthetic-documents-v1",
    dataset_sha256="1" * 64,
    preprocessing_version="normalized-whitespace-v1",
    pipeline_version="document-classifier-v1",
    artifact_sha256="2" * 64,
    evaluation_policy_version="classification-evaluation-policy-v1",
    evaluation_policy_sha256="3" * 64,
    evaluation_report_sha256="4" * 64,
)


@dataclass
class FakeFeedbackRepository:
    observations: tuple[FeedbackObservation, ...]
    error: Exception | None = None
    close_error: Exception | None = None
    calls: int = 0
    closed: bool = False
    private_filename: str = "do-not-export-private-filename.pdf"
    private_actor: str = "do-not-export-private-actor"

    def list_feedback_observations(self) -> tuple[FeedbackObservation, ...]:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.observations

    def close(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


class FailingOutput(BytesIO):
    def write(self, data: bytes) -> int:
        raise OSError("private output path")


def corpus_digests() -> list[str]:
    value = json.loads(INVENTORY_PATH.read_bytes())
    return [sample["sourceSha256"] for sample in value["samples"]]


def observation(
    source_sha256: str,
    *,
    machine: str | None = "invoice",
    final: str | None = "invoice",
    outcome: str | None = "approved",
    processing_status: str = "completed",
    model_version: str | None = "document-type-v1",
    evidence: MeasuredModelEvidence | None = MEASURED_EVIDENCE,
) -> FeedbackObservation:
    return FeedbackObservation(
        source_sha256=source_sha256,
        processing_status=processing_status,
        machine_classification=machine,
        final_classification=final,
        review_outcome=outcome,
        model_version=model_version,
        model_evidence=evidence,
    )


def decoded_export(repository: FakeFeedbackRepository) -> tuple[dict[str, Any], bytes]:
    rendered = FeedbackExporter(
        repository=repository,
        inventory_path=INVENTORY_PATH,
    ).export_bytes()
    return json.loads(rendered), rendered


def test_feedback_inventory_binds_corpus_to_producer_upload_identity() -> None:
    inventory = json.loads(INVENTORY_PATH.read_bytes())
    corpus = json.loads(CORPUS_INVENTORY_PATH.read_bytes())

    assert inventory["corpusInventorySha256"] == sha256_bytes(CORPUS_INVENTORY_PATH.read_bytes())
    assert inventory["fixtureGeneratorSha256"] == sha256_bytes(FIXTURE_GENERATOR_PATH.read_bytes())
    assert [sample["sampleId"] for sample in inventory["samples"]] == [
        sample["sampleId"] for sample in corpus["samples"]
    ]
    for binding, corpus_sample in zip(inventory["samples"], corpus["samples"], strict=True):
        assert {
            key: binding[key] for key in ("familyId", "label", "license", "provenance", "sampleId")
        } == {
            key: corpus_sample[key]
            for key in ("familyId", "label", "license", "provenance", "sampleId")
        }
        assert binding["corpusSourceSha256"] == corpus_sample["sourceSha256"]
        fixture = build_fixture(REPOSITORY_ROOT / corpus_sample["path"])
        assert fixture.startswith(b"%PDF-")
        assert binding["sourceSha256"] == hashlib.sha256(fixture).hexdigest()


def test_export_is_closed_canonical_minimal_and_byte_identical() -> None:
    first_digest, second_digest = corpus_digests()[:2]
    approved = observation(first_digest)
    corrected = observation(
        second_digest,
        machine="invoice",
        final="report",
        outcome="corrected",
    )
    first_repository = FakeFeedbackRepository((corrected, approved))
    second_repository = FakeFeedbackRepository((approved, corrected))

    document, first = decoded_export(first_repository)
    _repeated, second = decoded_export(second_repository)

    assert first == second == canonical_json_bytes(document)
    assert first_repository.calls == second_repository.calls == 1
    assert document["schemaVersion"] == 1
    assert document["inventorySha256"] == sha256_bytes(INVENTORY_PATH.read_bytes())
    assert document["omissions"] == []
    candidates = document["candidates"]
    assert len(candidates) == 2
    assert [item["candidateId"] for item in candidates] == sorted(
        item["candidateId"] for item in candidates
    )
    assert {item["reviewOutcome"] for item in candidates} == {"approved", "corrected"}
    for candidate in candidates:
        unsigned_candidate = {
            key: value for key, value in candidate.items() if key != "candidateId"
        }
        assert candidate["candidateId"] == sha256_bytes(canonical_json_bytes(unsigned_candidate))
        assert set(candidate) == {
            "candidateId",
            "finalClassification",
            "machineClassification",
            "modelLineage",
            "reviewOutcome",
            "sourceSha256",
        }
    unsigned_export = {key: value for key, value in document.items() if key != "exportSha256"}
    assert document["exportSha256"] == sha256_bytes(canonical_json_bytes(unsigned_export))
    schema = json.loads(SCHEMA_PATH.read_bytes())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(document)


def test_export_uses_only_allowlisted_values() -> None:
    repository = FakeFeedbackRepository((observation(corpus_digests()[0]),))
    inventory = json.loads(INVENTORY_PATH.read_bytes())

    _document, rendered = decoded_export(repository)

    for forbidden in (
        repository.private_filename,
        repository.private_actor,
        "documentId",
        "jobId",
        "reviewerPrincipalId",
        "decidedAt",
        "objectKey",
        "originalFilename",
        "comment",
        inventory["samples"][0]["corpusSourceSha256"],
        inventory["samples"][0]["sampleId"],
    ):
        assert forbidden.encode() not in rendered


def test_ineligible_observations_have_only_stable_aggregate_reasons() -> None:
    digests = corpus_digests()
    incomplete = replace(MEASURED_EVIDENCE, artifact_sha256="invalid")
    repository = FakeFeedbackRepository(
        (
            observation(digests[0], processing_status="failed"),
            observation(digests[1], outcome=None),
            observation("invalid"),
            observation(digests[2], machine="other"),
            observation(digests[3], evidence=None),
            observation(digests[4], evidence=incomplete),
            observation("f" * 64),
        )
    )

    document, _rendered = decoded_export(repository)

    assert document["candidates"] == []
    assert document["omissions"] == [
        {"count": 1, "reason": "not-completed"},
        {"count": 1, "reason": "nonterminal-review"},
        {"count": 1, "reason": "invalid-source-identity"},
        {"count": 1, "reason": "unsupported-or-inconsistent-label"},
        {"count": 1, "reason": "legacy-unmeasured"},
        {"count": 1, "reason": "incomplete-lineage"},
        {"count": 1, "reason": "unknown-source"},
    ]


def test_duplicate_is_deduplicated_and_conflict_omits_the_source() -> None:
    duplicate_digest, conflicting_digest = corpus_digests()[:2]
    duplicate = observation(duplicate_digest)
    conflict_approved = observation(conflicting_digest)
    conflict_corrected = observation(
        conflicting_digest,
        machine="invoice",
        final="report",
        outcome="corrected",
    )
    repository = FakeFeedbackRepository(
        (conflict_corrected, duplicate, conflict_approved, duplicate)
    )

    document, rendered = decoded_export(repository)
    reversed_document, reversed_rendered = decoded_export(
        FakeFeedbackRepository(tuple(reversed(repository.observations)))
    )

    assert rendered == reversed_rendered
    assert document == reversed_document
    assert len(document["candidates"]) == 1
    assert document["candidates"][0]["sourceSha256"] == duplicate_digest
    assert document["omissions"] == [
        {"count": 1, "reason": "duplicate-observation"},
        {"count": 2, "reason": "conflicting-observation"},
    ]


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda value: value.update(schemaVersion=2), "FEEDBACK_INVALID_INVENTORY"),
        (
            lambda value: value["samples"][1].update(sampleId=value["samples"][0]["sampleId"]),
            "FEEDBACK_INVALID_INVENTORY_SAMPLE",
        ),
        (
            lambda value: value["samples"][1].update(
                sourceSha256=value["samples"][0]["sourceSha256"]
            ),
            "FEEDBACK_CONFLICTING_INVENTORY",
        ),
        (
            lambda value: value["samples"][1].update(
                corpusSourceSha256=value["samples"][0]["corpusSourceSha256"]
            ),
            "FEEDBACK_CONFLICTING_INVENTORY",
        ),
        (
            lambda value: value["samples"][0].update(provenance="private"),
            "FEEDBACK_INVALID_INVENTORY_SAMPLE",
        ),
        (
            lambda value: value["samples"][0].update(corpusSourceSha256="invalid"),
            "FEEDBACK_INVALID_INVENTORY_SAMPLE",
        ),
        (
            lambda value: value.update(fixtureGeneratorSha256="invalid"),
            "FEEDBACK_INVALID_INVENTORY",
        ),
        (
            lambda value: value.update(unexpected=True),
            "FEEDBACK_INVALID_INVENTORY",
        ),
        (
            lambda value: value["samples"].reverse(),
            "FEEDBACK_NONCANONICAL_INVENTORY",
        ),
    ],
)
def test_inventory_mutations_fail_closed(
    tmp_path: Path,
    mutation: Any,
    code: str,
) -> None:
    value = json.loads(INVENTORY_PATH.read_bytes())
    mutation(value)
    path = tmp_path / "corpus.json"
    path.write_bytes(canonical_json_bytes(value))

    with pytest.raises(FeedbackExportError, match=code):
        load_feedback_inventory(path)


@pytest.mark.parametrize("schema_version", [True, False])
def test_boolean_inventory_versions_fail_before_repository_projection(
    tmp_path: Path,
    schema_version: bool,
) -> None:
    value = json.loads(INVENTORY_PATH.read_bytes())
    value["schemaVersion"] = schema_version
    path = tmp_path / "corpus.json"
    path.write_bytes(canonical_json_bytes(value))
    repository = FakeFeedbackRepository((observation(corpus_digests()[0]),))

    with pytest.raises(FeedbackExportError, match="FEEDBACK_INVALID_INVENTORY"):
        FeedbackExporter(repository=repository, inventory_path=path).export_bytes()

    assert repository.calls == 0


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (b"{", "FEEDBACK_INVALID_INVENTORY_JSON"),
        (b"[]\n", "FEEDBACK_INVALID_INVENTORY"),
        (
            json.dumps(json.loads(INVENTORY_PATH.read_bytes())).encode(),
            "FEEDBACK_NONCANONICAL_INVENTORY",
        ),
    ],
)
def test_invalid_inventory_bytes_fail_closed(tmp_path: Path, content: bytes, code: str) -> None:
    path = tmp_path / "corpus.json"
    path.write_bytes(content)

    with pytest.raises(FeedbackExportError, match=code):
        load_feedback_inventory(path)


def test_database_failure_is_sanitized() -> None:
    repository = FakeFeedbackRepository((), error=RuntimeError("private database value"))

    with pytest.raises(FeedbackExportError) as raised:
        FeedbackExporter(repository=repository, inventory_path=INVENTORY_PATH).export_bytes()

    assert raised.value.code == "FEEDBACK_DATABASE_UNAVAILABLE"
    assert "private database value" not in str(raised.value)


def test_cli_writes_only_complete_export_and_closes_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = FakeFeedbackRepository((observation(corpus_digests()[0]),))
    monkeypatch.setattr(
        feedback_export_main,
        "get_settings",
        lambda: SimpleNamespace(database_url="postgresql+psycopg://synthetic"),
    )
    monkeypatch.setattr(feedback_export_main, "create_database_engine", lambda _url: object())
    monkeypatch.setattr(
        feedback_export_main,
        "SqlAlchemyFeedbackExportRepository",
        lambda *, engine: repository,
    )
    stdout = BytesIO()
    stderr = StringIO()

    result = feedback_export_main.main(
        ["--inventory", str(INVENTORY_PATH)],
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert json.loads(stdout.getvalue())["candidates"]
    assert stderr.getvalue() == ""
    assert repository.closed is True


@pytest.mark.parametrize("close_error", [None, RuntimeError("private close failure")])
def test_cli_failure_is_stable_and_emits_no_partial_document(
    monkeypatch: pytest.MonkeyPatch,
    close_error: Exception | None,
) -> None:
    repository = FakeFeedbackRepository(
        (),
        error=RuntimeError("private query failure"),
        close_error=close_error,
    )
    monkeypatch.setattr(
        feedback_export_main,
        "get_settings",
        lambda: SimpleNamespace(database_url="postgresql+psycopg://synthetic"),
    )
    monkeypatch.setattr(feedback_export_main, "create_database_engine", lambda _url: object())
    monkeypatch.setattr(
        feedback_export_main,
        "SqlAlchemyFeedbackExportRepository",
        lambda *, engine: repository,
    )
    stdout = BytesIO()
    stderr = StringIO()

    result = feedback_export_main.main(
        ["--inventory", str(INVENTORY_PATH)],
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 1
    assert stdout.getvalue() == b""
    assert stderr.getvalue() == "feedback export failed: FEEDBACK_DATABASE_UNAVAILABLE\n"
    assert "private" not in stderr.getvalue()
    assert repository.closed is True


def test_cli_close_failure_after_success_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = FakeFeedbackRepository(
        (observation(corpus_digests()[0]),),
        close_error=RuntimeError("private close failure"),
    )
    monkeypatch.setattr(
        feedback_export_main,
        "get_settings",
        lambda: SimpleNamespace(database_url="postgresql+psycopg://synthetic"),
    )
    monkeypatch.setattr(feedback_export_main, "create_database_engine", lambda _url: object())
    monkeypatch.setattr(
        feedback_export_main,
        "SqlAlchemyFeedbackExportRepository",
        lambda *, engine: repository,
    )
    stdout = BytesIO()
    stderr = StringIO()

    result = feedback_export_main.main(
        ["--inventory", str(INVENTORY_PATH)],
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 1
    assert stdout.getvalue() == b""
    assert stderr.getvalue() == "feedback export failed: FEEDBACK_EXPORT_FAILED\n"
    assert "private" not in stderr.getvalue()
    assert repository.closed is True


def test_cli_output_failure_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = FakeFeedbackRepository((observation(corpus_digests()[0]),))
    monkeypatch.setattr(
        feedback_export_main,
        "get_settings",
        lambda: SimpleNamespace(database_url="postgresql+psycopg://synthetic"),
    )
    monkeypatch.setattr(feedback_export_main, "create_database_engine", lambda _url: object())
    monkeypatch.setattr(
        feedback_export_main,
        "SqlAlchemyFeedbackExportRepository",
        lambda *, engine: repository,
    )
    stderr = StringIO()

    result = feedback_export_main.main(
        ["--inventory", str(INVENTORY_PATH)],
        stdout=FailingOutput(),
        stderr=stderr,
    )

    assert result == 1
    assert stderr.getvalue() == "feedback export failed: FEEDBACK_OUTPUT_UNAVAILABLE\n"
    assert "private" not in stderr.getvalue()
    assert repository.closed is True


def test_documented_module_invocation_has_portable_imports_and_stable_failure(
    tmp_path: Path,
) -> None:
    invalid_inventory = tmp_path / "invalid-inventory.json"
    invalid_inventory.write_bytes(b"{")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "reactorfront_api.feedback_export_main",
            "--inventory",
            str(invalid_inventory),
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.decode().splitlines() == [
        "feedback export failed: FEEDBACK_INVALID_INVENTORY_JSON"
    ]
    assert str(invalid_inventory).encode() not in result.stderr
