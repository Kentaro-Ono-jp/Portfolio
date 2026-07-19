from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest
from celery.exceptions import Reject, Retry

import reactorfront_ml.celery_app as celery_app
from reactorfront_ml.domain import (
    ProcessingFailureCode,
    PublishFailureCode,
    ResultPublishError,
    TransientProcessingError,
)
from reactorfront_ml.event_contracts import JsonSchemaEventValidator
from reactorfront_ml.rabbitmq import REQUEST_QUEUE, REQUEST_ROUTING_KEY

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_DIRECTORY = REPOSITORY_ROOT / "packages" / "contracts" / "events"
EXAMPLE_PATH = (
    REPOSITORY_ROOT
    / "packages"
    / "contracts"
    / "examples"
    / "events"
    / "document.processing.requested.v1.json"
)


@dataclass
class FakeProcessor:
    error: Exception | None = None
    failure_error: Exception | None = None
    processed: list[object] = field(default_factory=list)
    failures: list[ProcessingFailureCode] = field(default_factory=list)

    def process(self, request: object) -> None:
        self.processed.append(request)
        if self.error is not None:
            raise self.error

    def publish_failure(
        self,
        *,
        request: object,
        failure_code: ProcessingFailureCode,
    ) -> None:
        del request
        self.failures.append(failure_code)
        if self.failure_error is not None:
            raise self.failure_error


def payload() -> dict[str, object]:
    value = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def install_runtime(
    monkeypatch: pytest.MonkeyPatch,
    processor: FakeProcessor,
) -> None:
    runtime = SimpleNamespace(
        processor=processor,
        validator=JsonSchemaEventValidator(contract_directory=CONTRACT_DIRECTORY),
        classifier=SimpleNamespace(checksum="a" * 64),
    )
    monkeypatch.setattr(celery_app, "get_runtime", lambda: runtime)


def test_celery_configuration_preserves_late_ack_and_fixed_route() -> None:
    assert celery_app.app.conf.task_acks_late is True
    assert celery_app.app.conf.task_reject_on_worker_lost is True
    assert celery_app.app.conf.worker_hijack_root_logger is False
    assert celery_app.app.conf.worker_prefetch_multiplier == 1
    assert celery_app.app.conf.task_default_queue == REQUEST_QUEUE
    assert celery_app.app.conf.task_default_routing_key == REQUEST_ROUTING_KEY
    assert celery_app.app.conf.broker_transport_options["confirm_publish"] is True
    assert celery_app.app.conf.control_queue_durable is False
    assert celery_app.app.conf.control_queue_exclusive is True


def test_valid_request_runs_processor(monkeypatch: pytest.MonkeyPatch) -> None:
    processor = FakeProcessor()
    install_runtime(monkeypatch, processor)

    celery_app.process_document.run(payload())

    assert len(processor.processed) == 1


def test_invalid_request_is_rejected_without_requeue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processor = FakeProcessor()
    install_runtime(monkeypatch, processor)

    with pytest.raises(Reject) as raised:
        celery_app.process_document.run({"eventType": "invalid"})

    assert raised.value.requeue is False
    assert raised.value.__suppress_context__ is True
    assert not processor.processed


def test_invalid_request_logs_only_valid_available_identities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processor = FakeProcessor()
    install_runtime(monkeypatch, processor)
    observed: dict[str, object] = {}
    invalid = payload()
    invalid["eventType"] = "invalid"
    invalid["jobId"] = "not-a-uuid"

    monkeypatch.setattr(
        celery_app,
        "log_event",
        lambda *_args, **fields: observed.update(fields),
    )

    with pytest.raises(Reject):
        celery_app.process_document.run(invalid)

    assert observed["failureCode"] == "INVALID_REQUEST_EVENT"
    assert observed["requestedEventId"] == invalid["eventId"]
    assert observed["correlationId"] == invalid["correlationId"]
    assert observed["documentId"] == invalid["documentId"]
    assert "jobId" not in observed


def test_transient_failure_schedules_bounded_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processor = FakeProcessor(
        error=TransientProcessingError(code=ProcessingFailureCode.SOURCE_UNAVAILABLE)
    )
    install_runtime(monkeypatch, processor)
    observed: dict[str, object] = {}

    def retry(**values: object) -> Retry:
        observed.update(values)
        return Retry("retry")

    monkeypatch.setattr(celery_app.process_document, "retry", retry)

    with pytest.raises(Retry):
        celery_app.process_document.run(payload())

    assert observed["countdown"] == 1
    assert observed["max_retries"] == 2


def test_final_transient_attempt_publishes_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processor = FakeProcessor(
        error=TransientProcessingError(code=ProcessingFailureCode.SOURCE_UNAVAILABLE)
    )
    install_runtime(monkeypatch, processor)
    celery_app.process_document.push_request(retries=2)
    try:
        celery_app.process_document.run(payload())
    finally:
        celery_app.process_document.pop_request()

    assert processor.failures == [ProcessingFailureCode.SOURCE_UNAVAILABLE]


@pytest.mark.parametrize("during_failure_publish", [False, True])
def test_unconfirmed_result_requeues_same_requested_task(
    monkeypatch: pytest.MonkeyPatch,
    during_failure_publish: bool,
) -> None:
    publish_error = ResultPublishError(code=PublishFailureCode.CONFIRM_TIMEOUT)
    if during_failure_publish:
        processor = FakeProcessor(
            error=TransientProcessingError(code=ProcessingFailureCode.SOURCE_UNAVAILABLE),
            failure_error=publish_error,
        )
        retries = 2
    else:
        processor = FakeProcessor(error=publish_error)
        retries = 0
    install_runtime(monkeypatch, processor)
    celery_app.process_document.push_request(retries=retries)
    try:
        with pytest.raises(Reject) as raised:
            celery_app.process_document.run(payload())
    finally:
        celery_app.process_document.pop_request()

    assert raised.value.requeue is True


def test_unexpected_poison_failure_is_not_hot_requeued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processor = FakeProcessor(error=RuntimeError("private raw error"))
    install_runtime(monkeypatch, processor)

    with pytest.raises(Reject) as raised:
        celery_app.process_document.run(payload())

    assert raised.value.requeue is False
    assert raised.value.__suppress_context__ is True
