from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pika
import pytest

import reactorfront_api.rabbitmq as rabbitmq
from reactorfront_api.domain import OutboxLease, OutboxPublishError, PublishFailureCode
from reactorfront_api.rabbitmq import (
    REQUEST_EXCHANGE,
    REQUEST_QUEUE,
    REQUEST_ROUTING_KEY,
    REQUEST_TASK_NAME,
    PikaOutboxPublisher,
)

EVENT_ID = UUID("44444444-4444-4444-8444-444444444444")
JOB_ID = UUID("33333333-3333-4333-8333-333333333333")
CORRELATION_ID = UUID("11111111-1111-4111-8111-111111111111")
NOW = datetime(2026, 7, 19, 0, 0, tzinfo=UTC)


def lease() -> OutboxLease:
    return OutboxLease(
        event_id=EVENT_ID,
        event_type=REQUEST_ROUTING_KEY,
        job_id=JOB_ID,
        payload={
            "eventId": str(EVENT_ID),
            "eventType": REQUEST_ROUTING_KEY,
            "correlationId": str(CORRELATION_ID),
        },
        created_at=NOW,
        lease_owner="dispatcher-a",
        leased_until=NOW + timedelta(seconds=30),
        attempt_count=1,
    )


class FakeChannel:
    def __init__(self, *, publish_error: Exception | None = None) -> None:
        self.is_open = True
        self.publish_error = publish_error
        self.exchange_declarations: list[dict[str, object]] = []
        self.queue_declarations: list[dict[str, object]] = []
        self.bindings: list[dict[str, object]] = []
        self.confirmed = False
        self.publications: list[dict[str, object]] = []

    def exchange_declare(self, **values: object) -> None:
        self.exchange_declarations.append(values)

    def queue_declare(self, **values: object) -> None:
        self.queue_declarations.append(values)

    def queue_bind(self, **values: object) -> None:
        self.bindings.append(values)

    def confirm_delivery(self) -> None:
        self.confirmed = True

    def basic_publish(self, **values: object) -> None:
        if self.publish_error is not None:
            raise self.publish_error
        self.publications.append(values)


class FakeConnection:
    def __init__(
        self,
        channel: FakeChannel,
        *,
        close_error: Exception | None = None,
    ) -> None:
        self.selected_channel = channel
        self.close_error = close_error
        self.is_open = True
        self.closed = False

    def channel(self) -> FakeChannel:
        return self.selected_channel

    def close(self) -> None:
        if self.close_error is not None:
            raise self.close_error
        self.closed = True
        self.is_open = False


def install_connection(
    monkeypatch: pytest.MonkeyPatch,
    *,
    publish_error: Exception | None = None,
    close_error: Exception | None = None,
) -> tuple[FakeConnection, FakeChannel]:
    channel = FakeChannel(publish_error=publish_error)
    connection = FakeConnection(channel, close_error=close_error)
    monkeypatch.setattr(rabbitmq.pika, "BlockingConnection", lambda _parameters: connection)
    return connection, channel


def test_publish_declares_durable_topology_and_celery_v2_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection, channel = install_connection(monkeypatch)
    publisher = PikaOutboxPublisher(
        broker_url="amqp://guest:guest@localhost:5672/%2F",
        timeout_seconds=5,
    )

    publisher.publish(lease())

    assert connection.closed
    assert channel.confirmed
    assert channel.exchange_declarations == [
        {
            "exchange": REQUEST_EXCHANGE,
            "exchange_type": "direct",
            "durable": True,
            "auto_delete": False,
        }
    ]
    assert channel.queue_declarations[0] == {
        "queue": REQUEST_QUEUE,
        "durable": True,
        "exclusive": False,
        "auto_delete": False,
    }
    assert channel.bindings[0]["routing_key"] == REQUEST_ROUTING_KEY

    publication = channel.publications[0]
    assert publication["mandatory"] is True
    properties = publication["properties"]
    assert isinstance(properties, pika.BasicProperties)
    assert properties.delivery_mode == 2
    assert properties.message_id == str(EVENT_ID)
    assert properties.correlation_id == str(EVENT_ID)
    assert properties.headers["task"] == REQUEST_TASK_NAME
    assert properties.headers["root_id"] == str(CORRELATION_ID)
    body = json.loads(publication["body"])
    assert body[0] == [lease().payload]
    assert body[1] == {}
    assert body[2] == {
        "callbacks": None,
        "errbacks": None,
        "chain": None,
        "chord": None,
    }


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (pika.exceptions.UnroutableError([]), PublishFailureCode.UNROUTABLE),
        (pika.exceptions.NackError([]), PublishFailureCode.CONFIRM_NACK),
        (
            pika.exceptions.ConnectionBlockedTimeout("confirm blocked"),
            PublishFailureCode.CONFIRM_TIMEOUT,
        ),
        (TimeoutError("confirm timed out"), PublishFailureCode.CONFIRM_TIMEOUT),
        (
            pika.exceptions.AMQPConnectionError("connection failed"),
            PublishFailureCode.BROKER_UNAVAILABLE,
        ),
    ],
)
def test_publish_maps_raw_failures_to_stable_codes(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected: PublishFailureCode,
) -> None:
    connection, _channel = install_connection(monkeypatch, publish_error=error)
    publisher = PikaOutboxPublisher(
        broker_url="amqp://guest:guest@localhost:5672/%2F",
        timeout_seconds=5,
    )

    with pytest.raises(OutboxPublishError) as captured:
        publisher.publish(lease())

    assert captured.value.code is expected
    assert connection.closed


def test_readiness_reports_connection_failure_and_closes_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publisher = PikaOutboxPublisher(
        broker_url="amqp://guest:guest@localhost:5672/%2F",
        timeout_seconds=5,
    )
    connection, channel = install_connection(monkeypatch)
    assert publisher.is_ready()
    assert channel.confirmed
    assert connection.closed

    monkeypatch.setattr(
        rabbitmq.pika,
        "BlockingConnection",
        lambda _parameters: (_ for _ in ()).throw(
            pika.exceptions.AMQPConnectionError("unavailable")
        ),
    )
    assert not publisher.is_ready()


def test_confirmed_publish_is_not_retried_only_because_close_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _connection, channel = install_connection(
        monkeypatch,
        close_error=pika.exceptions.AMQPConnectionError("close failed"),
    )
    publisher = PikaOutboxPublisher(
        broker_url="amqp://guest:guest@localhost:5672/%2F",
        timeout_seconds=5,
    )

    publisher.publish(lease())

    assert len(channel.publications) == 1


def test_connection_parameters_are_bounded() -> None:
    publisher = PikaOutboxPublisher(
        broker_url="amqp://guest:guest@localhost:5672/%2F",
        timeout_seconds=7,
    )
    parameters = publisher._connection_parameters()

    assert parameters.connection_attempts == 1
    assert parameters.retry_delay == 0
    assert parameters.socket_timeout == 7
    assert parameters.stack_timeout == 7
    assert parameters.blocked_connection_timeout == 7
