from __future__ import annotations

import logging
from typing import Any, Final
from uuid import UUID

from celery import Celery, Task
from celery.exceptions import Reject
from kombu import Exchange, Queue

from reactorfront_ml.domain import (
    InvalidRequestedEvent,
    ProcessingFailureCode,
    ResultPublishError,
    TransientProcessingError,
)
from reactorfront_ml.event_contracts import parse_requested_event
from reactorfront_ml.logging_config import configure_logging, log_event
from reactorfront_ml.model import MODEL_VERSION
from reactorfront_ml.rabbitmq import (
    DOCUMENT_EXCHANGE,
    REQUEST_QUEUE,
    REQUEST_ROUTING_KEY,
    REQUEST_TASK_NAME,
)
from reactorfront_ml.runtime import get_runtime
from reactorfront_ml.settings import get_settings

LOGGER = logging.getLogger(__name__)
MAX_PROCESSING_ATTEMPTS: Final = 3

settings = get_settings()
app = Celery("reactorfront_ml", broker=settings.rabbitmq_url.get_secret_value())
app.conf.update(
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    broker_transport_options={"confirm_publish": True},
    control_queue_exclusive=True,
    event_queue_exclusive=True,
    result_backend=None,
    task_acks_late=True,
    task_acks_on_failure_or_timeout=False,
    task_create_missing_queues=False,
    task_default_exchange=DOCUMENT_EXCHANGE,
    task_default_exchange_type="direct",
    task_default_queue=REQUEST_QUEUE,
    task_default_routing_key=REQUEST_ROUTING_KEY,
    task_ignore_result=True,
    task_publish_retry=True,
    task_publish_retry_policy={
        "max_retries": 3,
        "interval_start": 0,
        "interval_step": 0.5,
        "interval_max": 2,
    },
    task_queues=(
        Queue(
            REQUEST_QUEUE,
            exchange=Exchange(DOCUMENT_EXCHANGE, type="direct", durable=True),
            routing_key=REQUEST_ROUTING_KEY,
            durable=True,
        ),
    ),
    task_reject_on_worker_lost=True,
    task_serializer="json",
    worker_cancel_long_running_tasks_on_connection_loss=True,
    worker_hijack_root_logger=False,
    worker_prefetch_multiplier=1,
)
configure_logging()


@app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name=REQUEST_TASK_NAME,
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=MAX_PROCESSING_ATTEMPTS - 1,
)
def process_document(task: Task[Any, Any], payload: object) -> None:
    runtime = get_runtime()
    try:
        request = parse_requested_event(payload, validator=runtime.validator)
    except InvalidRequestedEvent:
        log_event(
            LOGGER,
            logging.ERROR,
            "ml_requested_event_rejected",
            **_safe_identity_fields(payload),
            failureCode="INVALID_REQUEST_EVENT",
            modelVersion=MODEL_VERSION,
            modelSha256=runtime.classifier.checksum,
        )
        raise Reject(reason="INVALID_REQUEST_EVENT", requeue=False) from None

    attempt = int(task.request.retries or 0) + 1
    fields: dict[str, object] = {
        "requestedEventId": str(request.event_id),
        "correlationId": str(request.correlation_id),
        "documentId": str(request.document_id),
        "jobId": str(request.job_id),
        "attempt": attempt,
        "modelVersion": MODEL_VERSION,
        "modelSha256": runtime.classifier.checksum,
    }
    try:
        runtime.processor.process(request)
    except TransientProcessingError as error:
        if attempt < MAX_PROCESSING_ATTEMPTS:
            log_event(
                LOGGER,
                logging.WARNING,
                "ml_processing_retry_scheduled",
                **fields,
                failureCode=error.code.value,
            )
            raise task.retry(
                exc=error,
                countdown=2 ** (attempt - 1),
                max_retries=MAX_PROCESSING_ATTEMPTS - 1,
            ) from error
        try:
            runtime.processor.publish_failure(
                request=request,
                failure_code=ProcessingFailureCode.SOURCE_UNAVAILABLE,
            )
        except ResultPublishError as publish_error:
            _reject_for_publish_failure(publish_error, fields=fields)
    except ResultPublishError as error:
        _reject_for_publish_failure(error, fields=fields)
    except Reject:
        raise
    except Exception:
        log_event(
            LOGGER,
            logging.ERROR,
            "ml_processing_poison_failure",
            **fields,
            failureCode=ProcessingFailureCode.MODEL_INFERENCE_FAILED.value,
        )
        raise Reject(reason="MODEL_INFERENCE_FAILED", requeue=False) from None


def _reject_for_publish_failure(
    error: ResultPublishError,
    *,
    fields: dict[str, object],
) -> None:
    log_event(
        LOGGER,
        logging.ERROR,
        "ml_result_publish_unconfirmed",
        **fields,
        failureCode=error.code.value,
    )
    raise Reject(reason=error.code.value, requeue=True) from None


def _safe_identity_fields(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    fields: dict[str, object] = {}
    for source, target in (
        ("eventId", "requestedEventId"),
        ("correlationId", "correlationId"),
        ("documentId", "documentId"),
        ("jobId", "jobId"),
    ):
        try:
            fields[target] = str(UUID(str(payload[source])))
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
    return fields
