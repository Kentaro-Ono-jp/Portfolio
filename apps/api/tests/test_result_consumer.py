from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from uuid import UUID, uuid5

import pika
import pytest

import reactorfront_api.result_consumer as result_consumer
from reactorfront_api.domain import (
    ResultApplyOutcome,
    ResultEvent,
    ResultEventFailureCode,
    ResultEventInvariantError,
)
from reactorfront_api.event_contracts import JsonSchemaEventValidator
from reactorfront_api.result_consumer import (
    DeliveryAction,
    PikaResultEventConsumer,
    ResultEventMessageHandler,
)

CONTRACTS = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "events"
REQUEST_EVENT_ID = UUID("44444444-4444-4444-8444-444444444444")
CORRELATION_ID = UUID("11111111-1111-4111-8111-111111111111")
DOCUMENT_ID = UUID("22222222-2222-4222-8222-222222222222")
JOB_ID = UUID("33333333-3333-4333-8333-333333333333")
OCCURRED_AT = datetime(2026, 7, 20, 0, 0, tzinfo=UTC)


@dataclass
class FakeResultRepository:
    outcome: ResultApplyOutcome = ResultApplyOutcome.APPLIED
    error: Exception | None = None
    ready: bool = True
    applied: list[ResultEvent] = field(default_factory=list)
    closed: bool = False

    def apply(self, event: ResultEvent) -> ResultApplyOutcome:
        if self.error is not None:
            raise self.error
        self.applied.append(event)
        return self.outcome

    def is_ready(self) -> bool:
        return self.ready

    def close(self) -> None:
        self.closed = True


def payload(*, event_type: str = "document.processing.completed.v1") -> dict[str, object]:
    value: dict[str, object] = {
        "eventId": str(uuid5(REQUEST_EVENT_ID, event_type)),
        "eventType": event_type,
        "occurredAt": "2026-07-20T00:00:00Z",
        "correlationId": str(CORRELATION_ID),
        "documentId": str(DOCUMENT_ID),
        "jobId": str(JOB_ID),
        "objectKey": f"documents/{DOCUMENT_ID}/source.pdf",
        "sourceSha256": "a" * 64,
        "modelVersion": "document-type-v1",
    }
    if event_type == "document.processing.completed.v1":
        value.update(classification="invoice", confidence=0.9876)
    elif event_type == "document.processing.failed.v1":
        value["failureCode"] = "SOURCE_DIGEST_MISMATCH"
    return value


def properties(value: dict[str, object]) -> pika.BasicProperties:
    return pika.BasicProperties(
        content_type="application/json",
        content_encoding="utf-8",
        delivery_mode=2,
        correlation_id=str(value["correlationId"]),
        message_id=str(value["eventId"]),
        timestamp=int(OCCURRED_AT.timestamp()),
        type=str(value["eventType"]),
        app_id="reactorfront-ml-worker",
        headers={
            "correlationId": str(value["correlationId"]),
            "documentId": str(value["documentId"]),
            "jobId": str(value["jobId"]),
        },
    )


def handler(repository: FakeResultRepository) -> ResultEventMessageHandler:
    return ResultEventMessageHandler(
        repository=repository,
        validator=JsonSchemaEventValidator(contract_directory=CONTRACTS),
    )


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (ResultApplyOutcome.APPLIED, DeliveryAction.ACKNOWLEDGE),
        (ResultApplyOutcome.DUPLICATE, DeliveryAction.ACKNOWLEDGE),
        (ResultApplyOutcome.DEFERRED, DeliveryAction.REQUEUE),
    ],
)
def test_handler_maps_repository_outcome_to_delivery_action(
    outcome: ResultApplyOutcome,
    expected: DeliveryAction,
) -> None:
    value = payload()
    repository = FakeResultRepository(outcome=outcome)

    assert (
        handler(repository).handle(
            body=json.dumps(value).encode(),
            properties=properties(value),
        )
        is expected
    )
    assert len(repository.applied) == 1


@pytest.mark.parametrize(
    "body",
    [
        b"not-json",
        json.dumps({"eventType": "unknown.v1"}).encode(),
        b"\xff",
    ],
)
def test_handler_rejects_invalid_body(body: bytes) -> None:
    repository = FakeResultRepository()

    assert (
        handler(repository).handle(body=body, properties=pika.BasicProperties())
        is DeliveryAction.REJECT
    )
    assert repository.applied == []


def test_handler_rejects_non_finite_confidence() -> None:
    value = payload()
    value["confidence"] = float("nan")

    assert (
        handler(FakeResultRepository()).handle(
            body=json.dumps(value).encode(),
            properties=properties(value),
        )
        is DeliveryAction.REJECT
    )


def test_handler_rejects_inconsistent_transport_metadata() -> None:
    value = payload()
    metadata = properties(value)
    metadata.message_id = str(UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"))
    repository = FakeResultRepository()

    assert (
        handler(repository).handle(
            body=json.dumps(value).encode(),
            properties=metadata,
        )
        is DeliveryAction.REJECT
    )
    assert repository.applied == []


def test_handler_rejects_missing_transport_headers() -> None:
    value = payload()
    metadata = properties(value)
    metadata.headers = None

    assert (
        handler(FakeResultRepository()).handle(
            body=json.dumps(value).encode(),
            properties=metadata,
        )
        is DeliveryAction.REJECT
    )


def test_handler_rejects_invariant_and_requeues_transient_failure() -> None:
    value = payload()
    repository = FakeResultRepository(
        error=ResultEventInvariantError(code=ResultEventFailureCode.TERMINAL_CONFLICT)
    )
    candidate = handler(repository)

    assert (
        candidate.handle(body=json.dumps(value).encode(), properties=properties(value))
        is DeliveryAction.REJECT
    )
    repository.error = ConnectionError("database unavailable")
    assert (
        candidate.handle(body=json.dumps(value).encode(), properties=properties(value))
        is DeliveryAction.REQUEUE
    )


def test_handler_readiness_and_close_delegate_to_repository() -> None:
    repository = FakeResultRepository(ready=False)
    candidate = handler(repository)

    assert not candidate.is_ready()
    candidate.close()
    assert repository.closed


class FakeTopologyChannel:
    def __init__(self) -> None:
        self.exchanges: list[dict[str, object]] = []
        self.queues: list[dict[str, object]] = []
        self.bindings: list[dict[str, object]] = []

    def exchange_declare(self, **values: object) -> None:
        self.exchanges.append(values)

    def queue_declare(self, **values: object) -> None:
        self.queues.append(values)

    def queue_bind(self, **values: object) -> None:
        self.bindings.append(values)


class FakeReadinessConnection:
    def __init__(self, channel: FakeTopologyChannel) -> None:
        self.selected_channel = channel
        self.closed = False

    def channel(self) -> FakeTopologyChannel:
        return self.selected_channel

    def close(self) -> None:
        self.closed = True


def consumer(repository: FakeResultRepository) -> PikaResultEventConsumer:
    return PikaResultEventConsumer(
        broker_url="amqp://guest:guest@localhost:5672/%2F",
        timeout_seconds=2,
        prefetch_count=1,
        requeue_delay_seconds=0.25,
        reconnect_delay_seconds=1,
        handler=handler(repository),
    )


def test_consumer_readiness_declares_durable_result_topology(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channel = FakeTopologyChannel()
    connection = FakeReadinessConnection(channel)
    monkeypatch.setattr(
        result_consumer.pika,
        "BlockingConnection",
        lambda _parameters: connection,
    )

    assert consumer(FakeResultRepository()).is_ready()
    assert connection.closed
    assert channel.exchanges == [
        {
            "exchange": "reactorfront.documents.v1",
            "exchange_type": "direct",
            "durable": True,
            "auto_delete": False,
        }
    ]
    assert channel.queues[0]["queue"] == "reactorfront.document-processing.events.v1"
    assert [binding["routing_key"] for binding in channel.bindings] == [
        "document.processing.started.v1",
        "document.processing.completed.v1",
        "document.processing.failed.v1",
    ]


def test_consumer_readiness_fails_closed() -> None:
    assert not consumer(FakeResultRepository(ready=False)).is_ready()


def test_consumer_readiness_handles_broker_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        result_consumer.pika,
        "BlockingConnection",
        lambda _parameters: (_ for _ in ()).throw(OSError("broker unavailable")),
    )

    assert not consumer(FakeResultRepository()).is_ready()


class FakeDeliveryHandler:
    def __init__(self) -> None:
        self.actions = iter(
            [
                DeliveryAction.ACKNOWLEDGE,
                DeliveryAction.REJECT,
                DeliveryAction.REQUEUE,
            ]
        )

    def handle(self, *, body: bytes, properties: pika.BasicProperties) -> DeliveryAction:
        assert body == b"body"
        assert properties.content_type == "application/json"
        return next(self.actions)

    @staticmethod
    def is_ready() -> bool:
        return True

    @staticmethod
    def close() -> None:
        return None


class FakeConsumingChannel(FakeTopologyChannel):
    def __init__(self) -> None:
        super().__init__()
        self.is_open = True
        self.prefetch_count: int | None = None
        self.acknowledged: list[int] = []
        self.rejected: list[tuple[int, bool]] = []
        self.nacked: list[tuple[int, bool]] = []
        self.cancelled = False

    def basic_qos(self, *, prefetch_count: int) -> None:
        self.prefetch_count = prefetch_count

    def consume(self, **_values: object) -> object:
        message = pika.BasicProperties(content_type="application/json")
        return iter(
            [
                (SimpleNamespace(delivery_tag=1), message, b"body"),
                (SimpleNamespace(delivery_tag=2), message, b"body"),
                (SimpleNamespace(delivery_tag=3), message, b"body"),
            ]
        )

    def basic_ack(self, *, delivery_tag: int) -> None:
        self.acknowledged.append(delivery_tag)

    def basic_reject(self, *, delivery_tag: int, requeue: bool) -> None:
        self.rejected.append((delivery_tag, requeue))

    def basic_nack(self, *, delivery_tag: int, requeue: bool) -> None:
        self.nacked.append((delivery_tag, requeue))

    def cancel(self) -> None:
        self.cancelled = True


class FakeConsumingConnection(FakeReadinessConnection):
    def __init__(self, channel: FakeConsumingChannel) -> None:
        super().__init__(channel)
        self.is_open = True

    def close(self) -> None:
        super().close()
        self.is_open = False


def test_consumer_acknowledges_rejects_and_requeues_deliveries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channel = FakeConsumingChannel()
    connection = FakeConsumingConnection(channel)
    waits: list[float] = []
    candidate = PikaResultEventConsumer(
        broker_url="amqp://guest:guest@localhost:5672/%2F",
        timeout_seconds=2,
        prefetch_count=3,
        requeue_delay_seconds=0.25,
        reconnect_delay_seconds=1,
        handler=FakeDeliveryHandler(),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(
        result_consumer.pika,
        "BlockingConnection",
        lambda _parameters: connection,
    )

    candidate._consume_connection(
        stop_event=Event(),
        wait=lambda seconds: waits.append(seconds) or False,
    )

    assert channel.prefetch_count == 3
    assert channel.acknowledged == [1]
    assert channel.rejected == [(2, False)]
    assert channel.nacked == [(3, True)]
    assert waits == [0.25]
    assert channel.cancelled
    assert not connection.is_open


def test_consumer_run_reconnects_after_broker_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop_event = Event()
    candidate = consumer(FakeResultRepository())

    def fail_once(**_values: object) -> None:
        stop_event.set()
        raise OSError("broker unavailable")

    monkeypatch.setattr(candidate, "_consume_connection", fail_once)
    candidate.run_forever(stop_event)
