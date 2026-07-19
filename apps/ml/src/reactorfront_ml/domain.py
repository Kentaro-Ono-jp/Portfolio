from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class ProcessingFailureCode(StrEnum):
    INVALID_PDF = "INVALID_PDF"
    MODEL_INFERENCE_FAILED = "MODEL_INFERENCE_FAILED"
    PDF_ENCRYPTED = "PDF_ENCRYPTED"
    PDF_PAGE_COUNT_UNSUPPORTED = "PDF_PAGE_COUNT_UNSUPPORTED"
    PDF_TEXT_EXTRACTION_FAILED = "PDF_TEXT_EXTRACTION_FAILED"
    SOURCE_DIGEST_MISMATCH = "SOURCE_DIGEST_MISMATCH"
    SOURCE_OBJECT_NOT_FOUND = "SOURCE_OBJECT_NOT_FOUND"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"


class PublishFailureCode(StrEnum):
    BROKER_UNAVAILABLE = "BROKER_UNAVAILABLE"
    CONFIRM_NACK = "CONFIRM_NACK"
    CONFIRM_TIMEOUT = "CONFIRM_TIMEOUT"
    PUBLISH_UNKNOWN = "PUBLISH_UNKNOWN"
    UNROUTABLE = "UNROUTABLE"


class InvalidRequestedEvent(Exception):
    pass


class PermanentProcessingError(Exception):
    def __init__(self, *, code: ProcessingFailureCode) -> None:
        super().__init__(code.value)
        self.code = code


class TransientProcessingError(Exception):
    def __init__(self, *, code: ProcessingFailureCode) -> None:
        super().__init__(code.value)
        self.code = code


class ResultPublishError(Exception):
    def __init__(self, *, code: PublishFailureCode) -> None:
        super().__init__(code.value)
        self.code = code


@dataclass(frozen=True, slots=True)
class ProcessingRequest:
    event_id: UUID
    occurred_at: datetime
    correlation_id: UUID
    document_id: UUID
    job_id: UUID
    object_key: str
    source_sha256: str


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    classification: str
    confidence: float
    model_version: str


class SourceStorage(Protocol):
    def get(self, *, object_key: str) -> bytes: ...

    def is_ready(self) -> bool: ...


class DocumentClassification(Protocol):
    checksum: str

    def classify(self, text: str) -> ClassificationResult: ...


class EventContractValidator(Protocol):
    def validate(self, *, event_type: str, payload: dict[str, object]) -> None: ...


class ResultEventPublisher(Protocol):
    def publish(self, *, event_type: str, payload: dict[str, object]) -> None: ...

    def is_ready(self) -> bool: ...
