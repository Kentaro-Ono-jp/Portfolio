from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID

import pytest

from reactorfront_ml.domain import (
    ClassificationResult,
    PermanentProcessingError,
    ProcessingFailureCode,
    ProcessingRequest,
    PublishFailureCode,
    ResultPublishError,
    TransientProcessingError,
)
from reactorfront_ml.events import ResultEventFactory
from reactorfront_ml.lineage import RuntimeModelEvidence
from reactorfront_ml.model import MODEL_VERSION, ModelArtifactError
from reactorfront_ml.processor import DocumentProcessor
from tests.fakes import FakeClassifier, FakePublisher, FakeStorage, FakeValidator

PDF_TEXT = "INVOICE invoice total amount due tax payment"
PDF_CONTENT = b"synthetic-pdf-content"
NOW = datetime(2026, 7, 19, 3, 0, tzinfo=UTC)
MODEL_EVIDENCE = RuntimeModelEvidence(
    dataset_version="reactorfront-synthetic-documents-v1",
    dataset_sha256="e" * 64,
    preprocessing_version="nfkc-ascii-alphanumeric-bow-v1",
    pipeline_version="pytorch-multinomial-naive-bayes-linear-v1",
    artifact_sha256="a" * 64,
    evaluation_policy_version="document-classification-evaluation-v1",
    evaluation_policy_sha256="b" * 64,
    evaluation_report_sha256="c" * 64,
)


def request(*, digest: str | None = None) -> ProcessingRequest:
    return ProcessingRequest(
        event_id=UUID("11111111-1111-4111-8111-111111111111"),
        occurred_at=NOW,
        correlation_id=UUID("22222222-2222-4222-8222-222222222222"),
        document_id=UUID("33333333-3333-4333-8333-333333333333"),
        job_id=UUID("44444444-4444-4444-8444-444444444444"),
        object_key="documents/33333333/source.pdf",
        source_sha256=digest or hashlib.sha256(PDF_CONTENT).hexdigest(),
    )


def processor(
    *,
    storage: FakeStorage | None = None,
    classifier: FakeClassifier | None = None,
    validator: FakeValidator | None = None,
    publisher: FakePublisher | None = None,
) -> tuple[DocumentProcessor, FakeStorage, FakeClassifier, FakeValidator, FakePublisher]:
    selected_storage = storage or FakeStorage(content=PDF_CONTENT)
    selected_classifier = classifier or FakeClassifier(
        result=ClassificationResult(
            classification="invoice",
            confidence=0.91,
            model_version=MODEL_VERSION,
        )
    )
    selected_validator = validator or FakeValidator()
    selected_publisher = publisher or FakePublisher()
    subject = DocumentProcessor(
        storage=selected_storage,
        classifier=selected_classifier,
        validator=selected_validator,
        publisher=selected_publisher,
        event_factory=ResultEventFactory(model_evidence=MODEL_EVIDENCE, clock=lambda: NOW),
    )
    return (
        subject,
        selected_storage,
        selected_classifier,
        selected_validator,
        selected_publisher,
    )


def test_success_confirms_started_before_completed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("reactorfront_ml.processor.extract_single_page_text", lambda _: PDF_TEXT)
    subject, storage, classifier, validator, publisher = processor()

    subject.process(request())

    assert storage.requested_keys == ["documents/33333333/source.pdf"]
    assert classifier.texts == [PDF_TEXT]
    assert [event_type for event_type, _ in publisher.published] == [
        "document.processing.started.v1",
        "document.processing.completed.v2",
    ]
    assert publisher.published == validator.validated
    completed = publisher.published[-1][1]
    assert completed["classification"] == "invoice"
    assert completed["confidence"] == 0.91
    assert completed["modelEvidence"]["artifactSha256"] == "a" * 64


def test_started_completed_and_failed_events_use_the_runtime_selected_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_version = "document-type-candidate-v1"
    classifier = FakeClassifier(result=ClassificationResult("invoice", 0.91, selected_version))
    subject, _, _, _, publisher = processor(classifier=classifier)
    monkeypatch.setattr("reactorfront_ml.processor.extract_single_page_text", lambda _: PDF_TEXT)

    subject.process(request())
    assert all(payload["modelVersion"] == selected_version for _, payload in publisher.published)

    failed_subject, _, _, _, failed_publisher = processor(classifier=classifier)
    failed_subject.process(request(digest="0" * 64))
    assert all(
        payload["modelVersion"] == selected_version for _, payload in failed_publisher.published
    )


def test_digest_mismatch_publishes_sanitized_failed_event() -> None:
    subject, _, classifier, _, publisher = processor()

    subject.process(request(digest="0" * 64))

    assert not classifier.texts
    assert [event_type for event_type, _ in publisher.published] == [
        "document.processing.started.v1",
        "document.processing.failed.v1",
    ]
    assert publisher.published[-1][1]["failureCode"] == "SOURCE_DIGEST_MISMATCH"


def test_permanent_storage_failure_publishes_failed_event() -> None:
    storage = FakeStorage(
        error=PermanentProcessingError(code=ProcessingFailureCode.SOURCE_OBJECT_NOT_FOUND)
    )
    subject, _, _, _, publisher = processor(storage=storage)

    subject.process(request())

    assert publisher.published[-1][1]["failureCode"] == "SOURCE_OBJECT_NOT_FOUND"


def test_transient_failure_remains_retryable() -> None:
    storage = FakeStorage(
        error=TransientProcessingError(code=ProcessingFailureCode.SOURCE_UNAVAILABLE)
    )
    subject, _, _, _, publisher = processor(storage=storage)

    with pytest.raises(TransientProcessingError):
        subject.process(request())

    assert [event_type for event_type, _ in publisher.published] == [
        "document.processing.started.v1"
    ]


def test_model_failure_is_sanitized() -> None:
    classifier = FakeClassifier(
        result=ClassificationResult("invoice", 0.9, MODEL_VERSION),
        error=ModelArtifactError("raw model error"),
    )
    subject, _, _, _, publisher = processor(classifier=classifier)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("reactorfront_ml.processor.extract_single_page_text", lambda _: PDF_TEXT)
        subject.process(request())

    assert publisher.published[-1][1]["failureCode"] == "MODEL_INFERENCE_FAILED"


def test_unexpected_inference_failure_is_sanitized() -> None:
    classifier = FakeClassifier(
        result=ClassificationResult("invoice", 0.9, MODEL_VERSION),
        error=RuntimeError("raw private inference failure"),
    )
    subject, _, _, _, publisher = processor(classifier=classifier)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("reactorfront_ml.processor.extract_single_page_text", lambda _: PDF_TEXT)
        subject.process(request())

    assert publisher.published[-1][1]["failureCode"] == "MODEL_INFERENCE_FAILED"


def test_unconfirmed_started_event_prevents_storage_access() -> None:
    publisher = FakePublisher(error=ResultPublishError(code=PublishFailureCode.CONFIRM_TIMEOUT))
    subject, storage, _, _, _ = processor(publisher=publisher)

    with pytest.raises(ResultPublishError):
        subject.process(request())

    assert not storage.requested_keys
