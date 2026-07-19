from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from reactorfront_ml.domain import ResultEventPublisher, SourceStorage
from reactorfront_ml.event_contracts import JsonSchemaEventValidator
from reactorfront_ml.model import DocumentClassifier
from reactorfront_ml.processor import DocumentProcessor
from reactorfront_ml.rabbitmq import PikaResultEventPublisher
from reactorfront_ml.settings import Settings, get_settings
from reactorfront_ml.storage import S3SourceStorage


@dataclass(frozen=True, slots=True)
class WorkerRuntime:
    processor: DocumentProcessor
    validator: JsonSchemaEventValidator
    storage: SourceStorage
    publisher: ResultEventPublisher
    classifier: DocumentClassifier


def build_runtime(settings: Settings) -> WorkerRuntime:
    validator = JsonSchemaEventValidator(contract_directory=settings.event_contract_directory)
    storage = S3SourceStorage.create(
        endpoint_url=settings.s3_endpoint_url,
        access_key_id=settings.s3_access_key_id,
        secret_access_key=settings.s3_secret_access_key.get_secret_value(),
        bucket=settings.s3_bucket,
        region=settings.s3_region,
    )
    classifier = DocumentClassifier(
        artifact_path=settings.model_artifact_path,
        checksum_path=settings.model_checksum_path,
    )
    publisher = PikaResultEventPublisher(
        broker_url=settings.rabbitmq_url.get_secret_value(),
        timeout_seconds=settings.rabbitmq_timeout_seconds,
    )
    return WorkerRuntime(
        processor=DocumentProcessor(
            storage=storage,
            classifier=classifier,
            validator=validator,
            publisher=publisher,
        ),
        validator=validator,
        storage=storage,
        publisher=publisher,
        classifier=classifier,
    )


@lru_cache
def get_runtime() -> WorkerRuntime:
    return build_runtime(get_settings())
