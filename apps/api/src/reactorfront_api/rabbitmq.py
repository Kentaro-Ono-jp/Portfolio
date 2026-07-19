from __future__ import annotations

import json
from contextlib import suppress
from typing import Final, cast

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.exceptions import (
    AMQPError,
    AMQPHeartbeatTimeout,
    ConnectionBlockedTimeout,
    NackError,
    UnroutableError,
)

from reactorfront_api.domain import (
    OutboxLease,
    OutboxPublishError,
    PublishFailureCode,
)

REQUEST_EXCHANGE: Final = "reactorfront.documents.v1"
REQUEST_QUEUE: Final = "reactorfront.document-processing.requested.v1"
REQUEST_ROUTING_KEY: Final = "document.processing.requested.v1"
REQUEST_TASK_NAME: Final = "reactorfront_ml.process_document"


class PikaOutboxPublisher:
    def __init__(self, *, broker_url: str, timeout_seconds: float) -> None:
        self._broker_url = broker_url
        self._timeout_seconds = timeout_seconds

    def publish(self, lease: OutboxLease) -> None:
        connection: pika.BlockingConnection | None = None
        try:
            connection = pika.BlockingConnection(self._connection_parameters())
            channel = connection.channel()
            self._declare_topology(channel)
            channel.confirm_delivery()
            channel.basic_publish(
                exchange=REQUEST_EXCHANGE,
                routing_key=REQUEST_ROUTING_KEY,
                body=self._task_body(lease),
                properties=self._task_properties(lease),
                mandatory=True,
            )
        except OutboxPublishError:
            raise
        except UnroutableError as error:
            raise OutboxPublishError(code=PublishFailureCode.UNROUTABLE) from error
        except NackError as error:
            raise OutboxPublishError(code=PublishFailureCode.CONFIRM_NACK) from error
        except (AMQPHeartbeatTimeout, ConnectionBlockedTimeout, TimeoutError) as error:
            raise OutboxPublishError(code=PublishFailureCode.CONFIRM_TIMEOUT) from error
        except AMQPError as error:
            raise OutboxPublishError(code=PublishFailureCode.BROKER_UNAVAILABLE) from error
        finally:
            self._close_quietly(connection)

    def is_ready(self) -> bool:
        connection: pika.BlockingConnection | None = None
        try:
            connection = pika.BlockingConnection(self._connection_parameters())
            channel = connection.channel()
            self._declare_topology(channel)
            channel.confirm_delivery()
            return cast(bool, channel.is_open)
        except (AMQPError, TimeoutError):
            return False
        finally:
            self._close_quietly(connection)

    @staticmethod
    def _close_quietly(connection: pika.BlockingConnection | None) -> None:
        if connection is None or not connection.is_open:
            return
        with suppress(AMQPError):
            connection.close()

    def _connection_parameters(self) -> pika.URLParameters:
        parameters = pika.URLParameters(self._broker_url)
        parameters.connection_attempts = 1
        parameters.retry_delay = 0
        parameters.socket_timeout = self._timeout_seconds
        parameters.stack_timeout = self._timeout_seconds
        parameters.blocked_connection_timeout = self._timeout_seconds
        return parameters

    @staticmethod
    def _declare_topology(channel: BlockingChannel) -> None:
        channel.exchange_declare(
            exchange=REQUEST_EXCHANGE,
            exchange_type="direct",
            durable=True,
            auto_delete=False,
        )
        channel.queue_declare(
            queue=REQUEST_QUEUE,
            durable=True,
            exclusive=False,
            auto_delete=False,
        )
        channel.queue_bind(
            queue=REQUEST_QUEUE,
            exchange=REQUEST_EXCHANGE,
            routing_key=REQUEST_ROUTING_KEY,
        )

    @staticmethod
    def _task_body(lease: OutboxLease) -> bytes:
        embedded = {
            "callbacks": None,
            "errbacks": None,
            "chain": None,
            "chord": None,
        }
        body = [[lease.payload], {}, embedded]
        return json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")

    @staticmethod
    def _task_properties(lease: OutboxLease) -> pika.BasicProperties:
        event_id = str(lease.event_id)
        correlation_id = str(lease.payload["correlationId"])
        return pika.BasicProperties(
            content_type="application/json",
            content_encoding="utf-8",
            delivery_mode=2,
            correlation_id=event_id,
            message_id=event_id,
            timestamp=int(lease.created_at.timestamp()),
            type=lease.event_type,
            app_id="reactorfront-api-outbox",
            headers={
                "lang": "py",
                "task": REQUEST_TASK_NAME,
                "id": event_id,
                "root_id": correlation_id,
                "retries": 0,
                "argsrepr": f"(<{lease.event_type} event {event_id}>,)",
                "kwargsrepr": "{}",
                "origin": "api-outbox@reactorfront",
                "correlationId": correlation_id,
            },
        )
