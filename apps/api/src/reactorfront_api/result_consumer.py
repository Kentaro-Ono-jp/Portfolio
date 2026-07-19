from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from enum import StrEnum
from threading import Event
from typing import Final

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.exceptions import AMQPError
from pika.spec import BasicProperties

from reactorfront_api.domain import (
    InvalidResultEvent,
    ResultApplyOutcome,
    ResultEvent,
    ResultEventFailureCode,
    ResultEventInvariantError,
    ResultEventRepository,
    ResultEventType,
)
from reactorfront_api.event_contracts import JsonSchemaEventValidator, parse_result_event

LOGGER = logging.getLogger(__name__)

DOCUMENT_EXCHANGE: Final = "reactorfront.documents.v1"
RESULT_QUEUE: Final = "reactorfront.document-processing.events.v1"
RESULT_ROUTING_KEYS: Final = tuple(event_type.value for event_type in ResultEventType)


class DeliveryAction(StrEnum):
    ACKNOWLEDGE = "acknowledge"
    REJECT = "reject"
    REQUEUE = "requeue"


class ResultEventMessageHandler:
    def __init__(
        self,
        *,
        repository: ResultEventRepository,
        validator: JsonSchemaEventValidator,
    ) -> None:
        self._repository = repository
        self._validator = validator

    def handle(self, *, body: bytes, properties: BasicProperties) -> DeliveryAction:
        try:
            payload = json.loads(body.decode("utf-8"))
            event = parse_result_event(payload, validator=self._validator)
            self._validate_transport(event=event, properties=properties)
        except (InvalidResultEvent, json.JSONDecodeError, UnicodeDecodeError, TypeError):
            self._log(
                "result_event_rejected",
                level=logging.ERROR,
                failure_code=ResultEventFailureCode.INVALID_EVENT.value,
            )
            return DeliveryAction.REJECT

        fields = self._identity_fields(event)
        try:
            outcome = self._repository.apply(event)
        except ResultEventInvariantError as error:
            self._log(
                "result_event_rejected",
                level=logging.ERROR,
                failure_code=error.code.value,
                identity=fields,
            )
            return DeliveryAction.REJECT
        except Exception:
            self._log(
                "result_event_persistence_unavailable",
                level=logging.ERROR,
                failure_code="PERSISTENCE_UNAVAILABLE",
                identity=fields,
            )
            return DeliveryAction.REQUEUE

        if outcome is ResultApplyOutcome.DEFERRED:
            self._log("result_event_deferred", level=logging.WARNING, identity=fields)
            return DeliveryAction.REQUEUE

        self._log(
            "result_event_committed",
            apply_outcome=outcome.value,
            identity=fields,
        )
        return DeliveryAction.ACKNOWLEDGE

    def is_ready(self) -> bool:
        return self._repository.is_ready()

    def close(self) -> None:
        self._repository.close()

    @staticmethod
    def _validate_transport(*, event: ResultEvent, properties: BasicProperties) -> None:
        headers = properties.headers
        if not isinstance(headers, Mapping):
            raise InvalidResultEvent("Result event headers are missing")
        if (
            properties.content_type != "application/json"
            or properties.content_encoding != "utf-8"
            or properties.delivery_mode != 2
            or properties.message_id != str(event.event_id)
            or properties.correlation_id != str(event.correlation_id)
            or properties.type != event.event_type.value
            or properties.app_id != "reactorfront-ml-worker"
            or properties.timestamp != int(event.occurred_at.timestamp())
            or headers.get("correlationId") != str(event.correlation_id)
            or headers.get("documentId") != str(event.document_id)
            or headers.get("jobId") != str(event.job_id)
        ):
            raise InvalidResultEvent("Result event transport metadata is inconsistent")

    @staticmethod
    def _identity_fields(event: ResultEvent) -> dict[str, object]:
        return {
            "event_id": str(event.event_id),
            "event_type": event.event_type.value,
            "correlation_id": str(event.correlation_id),
            "document_id": str(event.document_id),
            "job_id": str(event.job_id),
        }

    @staticmethod
    def _log(
        event: str,
        *,
        level: int = logging.INFO,
        identity: Mapping[str, object] | None = None,
        **fields: object,
    ) -> None:
        LOGGER.log(
            level,
            json.dumps(
                {"event": event, **(identity or {}), **fields},
                separators=(",", ":"),
                sort_keys=True,
            ),
        )


class PikaResultEventConsumer:
    def __init__(
        self,
        *,
        broker_url: str,
        timeout_seconds: float,
        prefetch_count: int,
        requeue_delay_seconds: float,
        reconnect_delay_seconds: float,
        handler: ResultEventMessageHandler,
        wait: Callable[[float], bool] | None = None,
    ) -> None:
        self._broker_url = broker_url
        self._timeout_seconds = timeout_seconds
        self._prefetch_count = prefetch_count
        self._requeue_delay_seconds = requeue_delay_seconds
        self._reconnect_delay_seconds = reconnect_delay_seconds
        self._handler = handler
        self._wait = wait

    def run_forever(self, stop_event: Event) -> None:
        wait = self._wait or stop_event.wait
        self._log("result_consumer_started")
        while not stop_event.is_set():
            try:
                self._consume_connection(stop_event=stop_event, wait=wait)
            except (AMQPError, OSError):
                self._log(
                    "result_consumer_broker_unavailable",
                    level=logging.WARNING,
                    failure_code="BROKER_UNAVAILABLE",
                )
            if not stop_event.is_set():
                wait(self._reconnect_delay_seconds)
        self._log("result_consumer_stopped")

    def is_ready(self) -> bool:
        try:
            if not self._handler.is_ready():
                return False
            connection = pika.BlockingConnection(self._connection_parameters())
            try:
                self._declare_topology(connection.channel())
            finally:
                connection.close()
        except Exception:
            return False
        return True

    def close(self) -> None:
        self._handler.close()

    def _consume_connection(
        self,
        *,
        stop_event: Event,
        wait: Callable[[float], bool],
    ) -> None:
        connection = pika.BlockingConnection(self._connection_parameters())
        try:
            channel = connection.channel()
            self._declare_topology(channel)
            channel.basic_qos(prefetch_count=self._prefetch_count)
            for method, properties, body in channel.consume(
                queue=RESULT_QUEUE,
                auto_ack=False,
                inactivity_timeout=1,
            ):
                if stop_event.is_set():
                    break
                if method is None or properties is None or body is None:
                    continue
                action = self._handler.handle(body=body, properties=properties)
                delivery_tag = method.delivery_tag
                if action is DeliveryAction.ACKNOWLEDGE:
                    channel.basic_ack(delivery_tag=delivery_tag)
                elif action is DeliveryAction.REJECT:
                    channel.basic_reject(delivery_tag=delivery_tag, requeue=False)
                else:
                    wait(self._requeue_delay_seconds)
                    channel.basic_nack(delivery_tag=delivery_tag, requeue=True)
            if channel.is_open:
                channel.cancel()
        finally:
            if connection.is_open:
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
            exchange=DOCUMENT_EXCHANGE,
            exchange_type="direct",
            durable=True,
            auto_delete=False,
        )
        channel.queue_declare(
            queue=RESULT_QUEUE,
            durable=True,
            exclusive=False,
            auto_delete=False,
        )
        for routing_key in RESULT_ROUTING_KEYS:
            channel.queue_bind(
                queue=RESULT_QUEUE,
                exchange=DOCUMENT_EXCHANGE,
                routing_key=routing_key,
            )

    @staticmethod
    def _log(event: str, *, level: int = logging.INFO, **fields: object) -> None:
        LOGGER.log(
            level,
            json.dumps({"event": event, **fields}, separators=(",", ":"), sort_keys=True),
        )
