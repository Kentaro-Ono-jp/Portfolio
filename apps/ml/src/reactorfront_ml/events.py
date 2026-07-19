from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid5

from reactorfront_ml.domain import (
    ClassificationResult,
    ProcessingFailureCode,
    ProcessingRequest,
)

STARTED_EVENT_TYPE = "document.processing.started.v1"
COMPLETED_EVENT_TYPE = "document.processing.completed.v1"
FAILED_EVENT_TYPE = "document.processing.failed.v1"
RESULT_EVENT_TYPES = (STARTED_EVENT_TYPE, COMPLETED_EVENT_TYPE, FAILED_EVENT_TYPE)


class ResultEventFactory:
    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))

    def started(
        self,
        *,
        request: ProcessingRequest,
        model_version: str,
    ) -> dict[str, object]:
        return {
            **self._base(request=request, event_type=STARTED_EVENT_TYPE),
            "modelVersion": model_version,
        }

    def completed(
        self,
        *,
        request: ProcessingRequest,
        result: ClassificationResult,
    ) -> dict[str, object]:
        return {
            **self._base(request=request, event_type=COMPLETED_EVENT_TYPE),
            "modelVersion": result.model_version,
            "classification": result.classification,
            "confidence": result.confidence,
        }

    def failed(
        self,
        *,
        request: ProcessingRequest,
        model_version: str,
        failure_code: ProcessingFailureCode,
    ) -> dict[str, object]:
        return {
            **self._base(request=request, event_type=FAILED_EVENT_TYPE),
            "modelVersion": model_version,
            "failureCode": failure_code.value,
        }

    def _base(
        self,
        *,
        request: ProcessingRequest,
        event_type: str,
    ) -> dict[str, object]:
        occurred_at = self._clock().astimezone(UTC).isoformat().replace("+00:00", "Z")
        return {
            "eventId": str(uuid5(request.event_id, event_type)),
            "eventType": event_type,
            "occurredAt": occurred_at,
            "correlationId": str(request.correlation_id),
            "documentId": str(request.document_id),
            "jobId": str(request.job_id),
            "objectKey": request.object_key,
            "sourceSha256": request.source_sha256,
        }
