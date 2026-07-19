from __future__ import annotations

import json
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

import pika
import pytest
from pika.channel import Channel
from pika.frame import Method
from pika.spec import Basic, BasicProperties, Confirm, Exchange, Queue

import reactorfront_ml.rabbitmq as rabbitmq
from reactorfront_ml.domain import PublishFailureCode, ResultPublishError
from reactorfront_ml.events import RESULT_EVENT_TYPES
from reactorfront_ml.rabbitmq import (
    DOCUMENT_EXCHANGE,
    RESULT_QUEUE,
    PikaResultEventPublisher,
)

BROKER_URL = "amqp://guest:guest@localhost:5672/%2F"


def event() -> dict[str, object]:
    return {
        "eventId": "11111111-1111-4111-8111-111111111111",
        "eventType": "document.processing.completed.v1",
        "occurredAt": "2026-07-19T03:00:00Z",
        "correlationId": "22222222-2222-4222-8222-222222222222",
        "documentId": "33333333-3333-4333-8333-333333333333",
        "jobId": "44444444-4444-4444-8444-444444444444",
        "objectKey": "documents/33333333/source.pdf",
        "sourceSha256": "a" * 64,
        "modelVersion": "document-type-v1",
        "classification": "invoice",
        "confidence": 0.91,
    }


@dataclass
class FakeTimer:
    delay: float
    callback: Callable[[], None]
    active: bool = True


class FakeIOLoop:
    def __init__(self) -> None:
        self.ready: deque[Callable[[], None]] = deque()
        self.timers: list[FakeTimer] = []
        self.stopped = False
        self.closed = False
        self.stop_count = 0
        self.elapsed = 0.0

    def add_ready(self, callback: Callable[[], None]) -> None:
        self.ready.append(callback)

    def call_later(self, delay: float, callback: Callable[[], None]) -> FakeTimer:
        timer = FakeTimer(delay=delay, callback=callback)
        self.timers.append(timer)
        return timer

    @staticmethod
    def remove_timeout(timer: object) -> None:
        cast(FakeTimer, timer).active = False

    def start(self) -> None:
        while not self.stopped:
            if self.ready:
                self.ready.popleft()()
                continue
            active = [timer for timer in self.timers if timer.active]
            if not active:
                break
            timer = min(active, key=lambda candidate: candidate.delay)
            timer.active = False
            self.elapsed = max(self.elapsed, timer.delay)
            timer.callback()

    def stop(self) -> None:
        self.stop_count += 1
        self.stopped = True

    def close(self) -> None:
        self.closed = True


class FakeChannel:
    def __init__(
        self,
        *,
        confirmation: str = "ack",
        publish_error: Exception | None = None,
    ) -> None:
        self.confirmation = confirmation
        self.publish_error = publish_error
        self.exchange_declarations: list[dict[str, object]] = []
        self.queue_declarations: list[dict[str, object]] = []
        self.bindings: list[dict[str, object]] = []
        self.confirmed = False
        self.publications: list[dict[str, object]] = []
        self.confirmation_callback: Callable[[Method[Basic.Ack | Basic.Nack]], object] | None = None
        self.return_callback: (
            Callable[[Channel, Method[Basic.Return], BasicProperties, bytes], object] | None
        ) = None
        self.close_callback: Callable[[Channel, BaseException], object] | None = None

    def add_on_close_callback(
        self,
        callback: Callable[[Channel, BaseException], object],
    ) -> None:
        self.close_callback = callback

    def exchange_declare(self, **values: object) -> None:
        callback = cast(Callable[[Method[Exchange.DeclareOk]], object], values.pop("callback"))
        self.exchange_declarations.append(values)
        callback(Method(1, Exchange.DeclareOk()))

    def queue_declare(self, **values: object) -> None:
        callback = cast(Callable[[Method[Queue.DeclareOk]], object], values.pop("callback"))
        self.queue_declarations.append(values)
        callback(Method(1, Queue.DeclareOk()))

    def queue_bind(self, **values: object) -> None:
        callback = cast(Callable[[Method[Queue.BindOk]], object], values.pop("callback"))
        self.bindings.append(values)
        callback(Method(1, Queue.BindOk()))

    def add_on_return_callback(
        self,
        callback: Callable[[Channel, Method[Basic.Return], BasicProperties, bytes], object],
    ) -> None:
        self.return_callback = callback

    def confirm_delivery(
        self,
        ack_nack_callback: Callable[[Method[Basic.Ack | Basic.Nack]], object],
        callback: Callable[[Method[Confirm.SelectOk]], object] | None = None,
    ) -> None:
        self.confirmed = True
        self.confirmation_callback = ack_nack_callback
        assert callback is not None
        callback(Method(1, Confirm.SelectOk()))

    def basic_publish(self, **values: object) -> None:
        if self.publish_error is not None:
            raise self.publish_error
        self.publications.append(values)
        if self.confirmation == "timeout":
            return
        if self.confirmation == "unroutable":
            assert self.return_callback is not None
            self.return_callback(
                cast(Channel, self),
                Method(1, Basic.Return()),
                cast(BasicProperties, values["properties"]),
                cast(bytes, values["body"]),
            )
        self.deliver_confirmation(nack=self.confirmation == "nack")

    def deliver_confirmation(self, *, nack: bool = False) -> None:
        assert self.confirmation_callback is not None
        method: Basic.Ack | Basic.Nack = (
            Basic.Nack(delivery_tag=1) if nack else Basic.Ack(delivery_tag=1)
        )
        self.confirmation_callback(Method(1, method))


class FakeConnection:
    def __init__(
        self,
        *,
        ioloop: FakeIOLoop,
        channel: FakeChannel,
        on_open_callback: Callable[[object], object],
        on_open_error_callback: Callable[[object, BaseException], object],
        on_close_callback: Callable[[object, BaseException], object],
        open_error: Exception | None,
        close_error: Exception | None,
    ) -> None:
        self.ioloop = ioloop
        self.selected_channel = channel
        self.on_open_callback = on_open_callback
        self.on_open_error_callback = on_open_error_callback
        self.on_close_callback = on_close_callback
        self.open_error = open_error
        self.close_error = close_error
        self.is_closing = False
        self.is_closed = False
        self.closed = False
        self.aborted = False
        self.ioloop.add_ready(self._open)

    def _open(self) -> None:
        if self.open_error is not None:
            self.is_closed = True
            self.on_open_error_callback(self, self.open_error)
            return
        self.on_open_callback(self)

    def channel(self, *, on_open_callback: Callable[[object], object]) -> None:
        on_open_callback(self.selected_channel)

    def close(self, *, reply_code: int, reply_text: str) -> None:
        del reply_code, reply_text
        if self.close_error is not None:
            raise self.close_error
        self.is_closing = True
        self.ioloop.add_ready(self._finish_close)

    def _adapter_disconnect_stream(self) -> None:
        self.aborted = True
        self.is_closing = True
        self.ioloop.add_ready(self._finish_close)

    def _finish_close(self) -> None:
        self.is_closing = False
        self.is_closed = True
        self.closed = True
        self.on_close_callback(
            self,
            pika.exceptions.ConnectionClosedByClient(200, "test complete"),
        )


@dataclass
class InstalledConnection:
    ioloop: FakeIOLoop
    channel: FakeChannel
    connection: FakeConnection | None = None


def install_connection(
    monkeypatch: pytest.MonkeyPatch,
    *,
    confirmation: str = "ack",
    publish_error: Exception | None = None,
    open_error: Exception | None = None,
    close_error: Exception | None = None,
) -> InstalledConnection:
    installed = InstalledConnection(
        ioloop=FakeIOLoop(),
        channel=FakeChannel(confirmation=confirmation, publish_error=publish_error),
    )

    def connection_factory(**values: object) -> FakeConnection:
        connection = FakeConnection(
            ioloop=installed.ioloop,
            channel=installed.channel,
            on_open_callback=cast(Callable[[object], object], values["on_open_callback"]),
            on_open_error_callback=cast(
                Callable[[object, BaseException], object],
                values["on_open_error_callback"],
            ),
            on_close_callback=cast(
                Callable[[object, BaseException], object], values["on_close_callback"]
            ),
            open_error=open_error,
            close_error=close_error,
        )
        installed.connection = connection
        return connection

    monkeypatch.setattr(rabbitmq, "IOLoop", lambda: installed.ioloop)
    monkeypatch.setattr(rabbitmq, "SelectConnection", connection_factory)
    return installed


def test_publish_declares_durable_result_topology_and_persistent_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed = install_connection(monkeypatch)
    publisher = PikaResultEventPublisher(broker_url=BROKER_URL, timeout_seconds=5)

    publisher.publish(event_type="document.processing.completed.v1", payload=event())

    assert installed.connection is not None and installed.connection.closed
    assert installed.ioloop.closed
    assert installed.channel.exchange_declarations == [
        {
            "exchange": DOCUMENT_EXCHANGE,
            "exchange_type": "direct",
            "durable": True,
            "auto_delete": False,
        }
    ]
    assert installed.channel.queue_declarations == [
        {
            "queue": RESULT_QUEUE,
            "durable": True,
            "exclusive": False,
            "auto_delete": False,
        }
    ]
    assert [binding["routing_key"] for binding in installed.channel.bindings] == list(
        RESULT_EVENT_TYPES
    )
    publication = installed.channel.publications[0]
    assert publication["exchange"] == DOCUMENT_EXCHANGE
    assert publication["routing_key"] == "document.processing.completed.v1"
    assert publication["mandatory"] is True
    assert json.loads(cast(bytes, publication["body"])) == event()
    properties = cast(BasicProperties, publication["properties"])
    assert properties.delivery_mode == 2
    assert properties.message_id == event()["eventId"]
    assert properties.correlation_id == event()["correlationId"]
    assert properties.type == event()["eventType"]
    assert properties.headers["jobId"] == event()["jobId"]


@pytest.mark.parametrize(
    ("confirmation", "expected"),
    [
        ("unroutable", PublishFailureCode.UNROUTABLE),
        ("nack", PublishFailureCode.CONFIRM_NACK),
    ],
)
def test_negative_confirmations_have_stable_codes(
    monkeypatch: pytest.MonkeyPatch,
    confirmation: str,
    expected: PublishFailureCode,
) -> None:
    install_connection(monkeypatch, confirmation=confirmation)
    publisher = PikaResultEventPublisher(broker_url=BROKER_URL, timeout_seconds=5)

    with pytest.raises(ResultPublishError) as captured:
        publisher.publish(event_type="document.processing.completed.v1", payload=event())

    assert captured.value.code is expected


def test_confirm_timeout_aborts_and_ignores_late_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed = install_connection(monkeypatch, confirmation="timeout")
    publisher = PikaResultEventPublisher(broker_url=BROKER_URL, timeout_seconds=7)

    with pytest.raises(ResultPublishError) as captured:
        publisher.publish(event_type="document.processing.completed.v1", payload=event())

    assert captured.value.code is PublishFailureCode.CONFIRM_TIMEOUT
    assert installed.ioloop.elapsed == 7
    assert installed.connection is not None and installed.connection.aborted
    stop_count = installed.ioloop.stop_count
    installed.channel.deliver_confirmation()
    assert installed.ioloop.stop_count == stop_count


def test_connection_failure_and_readiness_are_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_connection(
        monkeypatch,
        open_error=pika.exceptions.AMQPConnectionError("connection failed"),
    )
    publisher = PikaResultEventPublisher(broker_url=BROKER_URL, timeout_seconds=5)

    assert not publisher.is_ready()

    installed = install_connection(monkeypatch)
    assert publisher.is_ready()
    assert installed.channel.confirmed
    assert not installed.channel.publications


def test_close_failure_after_ack_does_not_reclassify_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed = install_connection(
        monkeypatch,
        close_error=pika.exceptions.AMQPConnectionError("close failed"),
    )
    publisher = PikaResultEventPublisher(broker_url=BROKER_URL, timeout_seconds=5)

    publisher.publish(event_type="document.processing.completed.v1", payload=event())

    assert len(installed.channel.publications) == 1
    assert installed.connection is not None and installed.connection.aborted


def test_publisher_rejects_inconsistent_event_type() -> None:
    publisher = PikaResultEventPublisher(broker_url=BROKER_URL, timeout_seconds=5)

    with pytest.raises(ValueError, match="unsupported or inconsistent"):
        publisher.publish(event_type="document.processing.started.v1", payload=event())


def test_connection_parameters_have_bounded_attempts() -> None:
    publisher = PikaResultEventPublisher(broker_url=BROKER_URL, timeout_seconds=7)
    parameters = publisher._connection_parameters()

    assert parameters.connection_attempts == 1
    assert parameters.retry_delay == 0
    assert parameters.socket_timeout == 7
    assert parameters.stack_timeout == 7
    assert parameters.blocked_connection_timeout == 7


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (TimeoutError("publish timed out"), PublishFailureCode.CONFIRM_TIMEOUT),
        (RuntimeError("unexpected"), PublishFailureCode.PUBLISH_UNKNOWN),
    ],
)
def test_synchronous_publish_error_is_mapped(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected: PublishFailureCode,
) -> None:
    install_connection(monkeypatch, publish_error=error)
    publisher = PikaResultEventPublisher(broker_url=BROKER_URL, timeout_seconds=5)

    with pytest.raises(ResultPublishError) as captured:
        publisher.publish(event_type="document.processing.completed.v1", payload=event())

    assert captured.value.code is expected
