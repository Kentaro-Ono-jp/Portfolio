from __future__ import annotations

import hashlib
import logging

from reactorfront_ml.domain import (
    DocumentClassification,
    EventContractValidator,
    PermanentProcessingError,
    ProcessingFailureCode,
    ProcessingRequest,
    ResultEventPublisher,
    SourceStorage,
    TransientProcessingError,
)
from reactorfront_ml.events import (
    COMPLETED_EVENT_TYPE,
    FAILED_EVENT_TYPE,
    STARTED_EVENT_TYPE,
    ResultEventFactory,
)
from reactorfront_ml.logging_config import log_event
from reactorfront_ml.model import MODEL_VERSION, ModelArtifactError
from reactorfront_ml.pdf_processing import extract_single_page_text

LOGGER = logging.getLogger(__name__)


class DocumentProcessor:
    def __init__(
        self,
        *,
        storage: SourceStorage,
        classifier: DocumentClassification,
        validator: EventContractValidator,
        publisher: ResultEventPublisher,
        event_factory: ResultEventFactory | None = None,
    ) -> None:
        self._storage = storage
        self._classifier = classifier
        self._validator = validator
        self._publisher = publisher
        self._event_factory = event_factory or ResultEventFactory()

    def process(self, request: ProcessingRequest) -> None:
        self._publish(
            event_type=STARTED_EVENT_TYPE,
            payload=self._event_factory.started(
                request=request,
                model_version=MODEL_VERSION,
            ),
        )
        log_event(
            LOGGER,
            logging.INFO,
            "ml_processing_started",
            **self._fields(request),
            modelVersion=MODEL_VERSION,
            modelSha256=self._classifier.checksum,
        )
        try:
            content = self._storage.get(object_key=request.object_key)
            if hashlib.sha256(content).hexdigest() != request.source_sha256:
                raise PermanentProcessingError(code=ProcessingFailureCode.SOURCE_DIGEST_MISMATCH)
            text = extract_single_page_text(content)
            result = self._classifier.classify(text)
        except TransientProcessingError:
            raise
        except PermanentProcessingError as error:
            self.publish_failure(request=request, failure_code=error.code)
            return
        except ModelArtifactError:
            self.publish_failure(
                request=request,
                failure_code=ProcessingFailureCode.MODEL_INFERENCE_FAILED,
            )
            return
        except Exception:
            self.publish_failure(
                request=request,
                failure_code=ProcessingFailureCode.MODEL_INFERENCE_FAILED,
            )
            return

        self._publish(
            event_type=COMPLETED_EVENT_TYPE,
            payload=self._event_factory.completed(request=request, result=result),
        )
        log_event(
            LOGGER,
            logging.INFO,
            "ml_processing_completed",
            **self._fields(request),
            classification=result.classification,
            confidence=round(result.confidence, 8),
            modelVersion=result.model_version,
            modelSha256=self._classifier.checksum,
        )

    def publish_failure(
        self,
        *,
        request: ProcessingRequest,
        failure_code: ProcessingFailureCode,
    ) -> None:
        self._publish(
            event_type=FAILED_EVENT_TYPE,
            payload=self._event_factory.failed(
                request=request,
                model_version=MODEL_VERSION,
                failure_code=failure_code,
            ),
        )
        log_event(
            LOGGER,
            logging.WARNING,
            "ml_processing_failed",
            **self._fields(request),
            failureCode=failure_code.value,
            modelVersion=MODEL_VERSION,
            modelSha256=self._classifier.checksum,
        )

    def _publish(self, *, event_type: str, payload: dict[str, object]) -> None:
        self._validator.validate(event_type=event_type, payload=payload)
        self._publisher.publish(event_type=event_type, payload=payload)

    @staticmethod
    def _fields(request: ProcessingRequest) -> dict[str, object]:
        return {
            "requestedEventId": str(request.event_id),
            "correlationId": str(request.correlation_id),
            "documentId": str(request.document_id),
            "jobId": str(request.job_id),
        }
