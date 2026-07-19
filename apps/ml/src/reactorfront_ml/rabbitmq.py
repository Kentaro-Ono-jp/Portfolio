from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from typing import Final, Protocol, cast

import pika
from pika.adapters.select_connection import IOLoop, SelectConnection
from pika.channel import Channel
from pika.exceptions import AMQPError, AMQPHeartbeatTimeout, ConnectionBlockedTimeout
from pika.frame import Method
from pika.spec import Basic, BasicProperties, Confirm, Exchange, Queue

from reactorfront_ml.domain import PublishFailureCode, ResultPublishError
from reactorfront_ml.events import RESULT_EVENT_TYPES

DOCUMENT_EXCHANGE: Final = "reactorfront.documents.v1"
RESULT_QUEUE: Final = "reactorfront.document-processing.events.v1"
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


class PikaResultEventPublisher:
    def __init__(self, *, broker_url: str, timeout_seconds: float) -> None:
        self._broker_url = broker_url
        self._timeout_seconds = timeout_seconds

    def publish(self, *, event_type: str, payload: dict[str, object]) -> None:
        if event_type not in RESULT_EVENT_TYPES or payload.get("eventType") != event_type:
            raise ValueError("Result event type is unsupported or inconsistent")
        _PublishAttempt(
            parameters=self._connection_parameters(),
            timeout_seconds=self._timeout_seconds,
            event_type=event_type,
            payload=payload,
        ).run()

    def is_ready(self) -> bool:
        try:
            _PublishAttempt(
                parameters=self._connection_parameters(),
                timeout_seconds=self._timeout_seconds,
                event_type=None,
                payload=None,
            ).run()
        except ResultPublishError:
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
    def event_body(payload: dict[str, object]) -> bytes:
        return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

    @staticmethod
    def event_properties(*, event_type: str, payload: dict[str, object]) -> pika.BasicProperties:
        occurred_at = datetime.fromisoformat(str(payload["occurredAt"]))
        event_id = str(payload["eventId"])
        correlation_id = str(payload["correlationId"])
        return pika.BasicProperties(
            content_type="application/json",
            content_encoding="utf-8",
            delivery_mode=2,
            correlation_id=correlation_id,
            message_id=event_id,
            timestamp=int(occurred_at.timestamp()),
            type=event_type,
            app_id="reactorfront-ml-worker",
            headers={
                "correlationId": correlation_id,
                "documentId": str(payload["documentId"]),
                "jobId": str(payload["jobId"]),
            },
        )


class _PublishAttempt:
    """One result-event publication with a deadline on the same Pika I/O loop."""

    def __init__(
        self,
        *,
        parameters: pika.URLParameters,
        timeout_seconds: float,
        event_type: str | None,
        payload: dict[str, object] | None,
    ) -> None:
        self._parameters = parameters
        self._timeout_seconds = timeout_seconds
        self._event_type = event_type
        self._payload = payload
        self._ioloop = cast(_DeadlineIOLoop, IOLoop())
        self._connection: SelectConnection | None = None
        self._channel: Channel | None = None
        self._deadline_handle: object | None = None
        self._force_stop_handle: object | None = None
        self._binding_index = 0
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
            raise ResultPublishError(code=PublishFailureCode.PUBLISH_UNKNOWN)
        if self._failure_code is not None:
            raise ResultPublishError(code=self._failure_code)

    def _on_connection_open(self, connection: SelectConnection) -> None:
        if not self._result_ready:
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
            exchange=DOCUMENT_EXCHANGE,
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
            queue=RESULT_QUEUE,
            durable=True,
            exclusive=False,
            auto_delete=False,
            callback=self._on_queue_declared,
        )

    def _on_queue_declared(self, _frame: Method[Queue.DeclareOk]) -> None:
        self._binding_index = 0
        self._bind_current_routing_key()

    def _bind_current_routing_key(self) -> None:
        if self._result_ready or self._channel is None:
            return
        self._channel.queue_bind(
            queue=RESULT_QUEUE,
            exchange=DOCUMENT_EXCHANGE,
            routing_key=RESULT_EVENT_TYPES[self._binding_index],
            callback=self._on_queue_bound,
        )

    def _on_queue_bound(self, _frame: Method[Queue.BindOk]) -> None:
        if self._result_ready or self._channel is None:
            return
        self._binding_index += 1
        if self._binding_index < len(RESULT_EVENT_TYPES):
            self._bind_current_routing_key()
            return
        self._channel.add_on_return_callback(self._on_returned)
        self._channel.confirm_delivery(
            self._on_delivery_confirmation,
            callback=self._on_confirm_selected,
        )

    def _on_confirm_selected(self, _frame: Method[Confirm.SelectOk]) -> None:
        if self._result_ready or self._channel is None:
            return
        if self._event_type is None or self._payload is None:
            self._complete()
            return

        self._publication_sent = True
        try:
            self._channel.basic_publish(
                exchange=DOCUMENT_EXCHANGE,
                routing_key=self._event_type,
                body=PikaResultEventPublisher.event_body(self._payload),
                properties=PikaResultEventPublisher.event_properties(
                    event_type=self._event_type,
                    payload=self._payload,
                ),
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
