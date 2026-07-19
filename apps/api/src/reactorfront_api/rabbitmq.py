from __future__ import annotations

import json
from collections.abc import Callable
from typing import Final, Protocol, cast

import pika
from pika.adapters.select_connection import IOLoop, SelectConnection
from pika.channel import Channel
from pika.exceptions import (
    AMQPError,
    AMQPHeartbeatTimeout,
    ConnectionBlockedTimeout,
)
from pika.frame import Method
from pika.spec import Basic, BasicProperties, Confirm, Exchange, Queue

from reactorfront_api.domain import (
    OutboxLease,
    OutboxPublishError,
    PublishFailureCode,
)

REQUEST_EXCHANGE: Final = "reactorfront.documents.v1"
REQUEST_QUEUE: Final = "reactorfront.document-processing.requested.v1"
REQUEST_ROUTING_KEY: Final = "document.processing.requested.v1"
REQUEST_TASK_NAME: Final = "reactorfront_ml.process_document"

_FORCE_STOP_GRACE_SECONDS: Final = 0.05


class _AbortableSelectConnection(Protocol):
    def _adapter_disconnect_stream(self) -> None: ...


class _DeadlineIOLoop(Protocol):
    def call_later(self, delay: float, callback: Callable[[], None]) -> object: ...

    def remove_timeout(self, timeout_handle: object) -> None: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def close(self) -> None: ...


class PikaOutboxPublisher:
    def __init__(self, *, broker_url: str, timeout_seconds: float) -> None:
        self._broker_url = broker_url
        self._timeout_seconds = timeout_seconds

    def publish(self, lease: OutboxLease) -> None:
        _PublishAttempt(
            parameters=self._connection_parameters(),
            timeout_seconds=self._timeout_seconds,
            lease=lease,
        ).run()

    def is_ready(self) -> bool:
        try:
            _PublishAttempt(
                parameters=self._connection_parameters(),
                timeout_seconds=self._timeout_seconds,
                lease=None,
            ).run()
        except OutboxPublishError:
            return False
        return True

    def _connection_parameters(self) -> pika.URLParameters:
        parameters = pika.URLParameters(self._broker_url)
        parameters.connection_attempts = 1
        parameters.retry_delay = 0
        parameters.socket_timeout = self._timeout_seconds
        parameters.stack_timeout = self._timeout_seconds
        parameters.blocked_connection_timeout = self._timeout_seconds
        return parameters

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


class _PublishAttempt:
    """One connection-scoped confirm attempt with an actual wall-clock deadline."""

    def __init__(
        self,
        *,
        parameters: pika.URLParameters,
        timeout_seconds: float,
        lease: OutboxLease | None,
    ) -> None:
        self._parameters = parameters
        self._timeout_seconds = timeout_seconds
        self._lease = lease
        self._ioloop = cast(_DeadlineIOLoop, IOLoop())
        self._connection: SelectConnection | None = None
        self._channel: Channel | None = None
        self._deadline_handle: object | None = None
        self._force_stop_handle: object | None = None
        self._result_ready = False
        self._failure_code: PublishFailureCode | None = None
        self._publication_sent = False
        self._returned = False

    def run(self) -> None:
        self._deadline_handle = self._ioloop.call_later(
            self._timeout_seconds,
            self._on_deadline,
        )
        try:
            self._connection = SelectConnection(
                parameters=self._parameters,
                on_open_callback=self._on_connection_open,
                on_open_error_callback=self._on_connection_open_error,
                on_close_callback=self._on_connection_closed,
                custom_ioloop=cast(IOLoop, self._ioloop),
            )
            self._ioloop.start()
        except Exception as error:
            if not self._result_ready:
                self._result_ready = True
                self._failure_code = self._map_error(error)
            self._abort_connection()
        finally:
            self._cancel_timer("_deadline_handle")
            self._cancel_timer("_force_stop_handle")
            self._ioloop.close()

        if not self._result_ready:
            raise OutboxPublishError(code=PublishFailureCode.PUBLISH_UNKNOWN)
        if self._failure_code is not None:
            raise OutboxPublishError(code=self._failure_code)

    def _on_connection_open(self, connection: SelectConnection) -> None:
        if self._result_ready:
            return
        connection.channel(on_open_callback=self._on_channel_open)

    def _on_connection_open_error(
        self,
        _connection: SelectConnection,
        error: BaseException,
    ) -> None:
        self._complete(failure_code=self._map_error(error))

    def _on_connection_closed(
        self,
        _connection: SelectConnection,
        error: BaseException,
    ) -> None:
        if not self._result_ready:
            self._result_ready = True
            self._failure_code = self._map_error(error)
        self._cancel_timer("_deadline_handle")
        self._cancel_timer("_force_stop_handle")
        self._ioloop.stop()

    def _on_channel_open(self, channel: Channel) -> None:
        if self._result_ready:
            return
        self._channel = channel
        channel.add_on_close_callback(self._on_channel_closed)
        channel.exchange_declare(
            exchange=REQUEST_EXCHANGE,
            exchange_type="direct",
            durable=True,
            auto_delete=False,
            callback=self._on_exchange_declared,
        )

    def _on_channel_closed(self, _channel: Channel, error: BaseException) -> None:
        self._complete(failure_code=self._map_error(error))

    def _on_exchange_declared(self, _frame: Method[Exchange.DeclareOk]) -> None:
        if self._result_ready or self._channel is None:
            return
        self._channel.queue_declare(
            queue=REQUEST_QUEUE,
            durable=True,
            exclusive=False,
            auto_delete=False,
            callback=self._on_queue_declared,
        )

    def _on_queue_declared(self, _frame: Method[Queue.DeclareOk]) -> None:
        if self._result_ready or self._channel is None:
            return
        self._channel.queue_bind(
            queue=REQUEST_QUEUE,
            exchange=REQUEST_EXCHANGE,
            routing_key=REQUEST_ROUTING_KEY,
            callback=self._on_queue_bound,
        )

    def _on_queue_bound(self, _frame: Method[Queue.BindOk]) -> None:
        if self._result_ready or self._channel is None:
            return
        self._channel.add_on_return_callback(self._on_returned)
        self._channel.confirm_delivery(
            self._on_delivery_confirmation,
            callback=self._on_confirm_selected,
        )

    def _on_confirm_selected(self, _frame: Method[Confirm.SelectOk]) -> None:
        if self._result_ready or self._channel is None:
            return
        if self._lease is None:
            self._complete()
            return

        self._publication_sent = True
        try:
            self._channel.basic_publish(
                exchange=REQUEST_EXCHANGE,
                routing_key=REQUEST_ROUTING_KEY,
                body=PikaOutboxPublisher._task_body(self._lease),
                properties=PikaOutboxPublisher._task_properties(self._lease),
                mandatory=True,
            )
        except Exception as error:
            self._complete(failure_code=self._map_error(error))

    def _on_returned(
        self,
        _channel: Channel,
        _method: Method[Basic.Return],
        _properties: BasicProperties,
        _body: bytes,
    ) -> None:
        if not self._result_ready:
            self._returned = True

    def _on_delivery_confirmation(
        self,
        frame: Method[Basic.Ack | Basic.Nack],
    ) -> None:
        if self._result_ready:
            return
        if isinstance(frame.method, Basic.Nack):
            self._complete(failure_code=PublishFailureCode.CONFIRM_NACK)
            return
        if not isinstance(frame.method, Basic.Ack):
            self._complete(failure_code=PublishFailureCode.PUBLISH_UNKNOWN)
            return
        if self._returned:
            self._complete(failure_code=PublishFailureCode.UNROUTABLE)
            return
        self._complete()

    def _on_deadline(self) -> None:
        self._deadline_handle = None
        if not self._result_ready:
            self._result_ready = True
            self._failure_code = (
                PublishFailureCode.CONFIRM_TIMEOUT
                if self._publication_sent
                else PublishFailureCode.BROKER_UNAVAILABLE
            )
        self._abort_connection()
        self._force_stop_handle = self._ioloop.call_later(
            _FORCE_STOP_GRACE_SECONDS,
            self._force_stop,
        )

    def _complete(self, *, failure_code: PublishFailureCode | None = None) -> None:
        if self._result_ready:
            return
        self._result_ready = True
        self._failure_code = failure_code
        self._request_graceful_close()

    def _request_graceful_close(self) -> None:
        connection = self._connection
        if connection is None or connection.is_closed:
            self._ioloop.stop()
            return
        if connection.is_closing:
            return
        try:
            connection.close(reply_code=200, reply_text="publisher attempt complete")
        except Exception:
            self._abort_connection()

    def _abort_connection(self) -> None:
        connection = self._connection
        if connection is None or connection.is_closed:
            self._ioloop.stop()
            return
        try:
            cast(_AbortableSelectConnection, connection)._adapter_disconnect_stream()
        except Exception:
            self._ioloop.stop()

    def _force_stop(self) -> None:
        self._force_stop_handle = None
        self._abort_connection()
        self._ioloop.stop()

    def _cancel_timer(self, attribute: str) -> None:
        handle = cast(object | None, getattr(self, attribute))
        if handle is None:
            return
        self._ioloop.remove_timeout(handle)
        setattr(self, attribute, None)

    def _map_error(self, error: BaseException) -> PublishFailureCode:
        if isinstance(error, (AMQPHeartbeatTimeout, ConnectionBlockedTimeout, TimeoutError)):
            return (
                PublishFailureCode.CONFIRM_TIMEOUT
                if self._publication_sent
                else PublishFailureCode.BROKER_UNAVAILABLE
            )
        if isinstance(error, AMQPError):
            return PublishFailureCode.BROKER_UNAVAILABLE
        return PublishFailureCode.PUBLISH_UNKNOWN
