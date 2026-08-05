from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from reactorfront_ml.domain import ResultEventPublisher, SourceStorage
from reactorfront_ml.event_contracts import JsonSchemaEventValidator
from reactorfront_ml.events import ResultEventFactory
from reactorfront_ml.lineage import load_runtime_model_evidence
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
    model_evidence = load_runtime_model_evidence(
        settings.champion_evaluation_report_path,
        repository_root=settings.evaluation_repository_root,
        dataset_snapshot_path=settings.evaluation_dataset_snapshot_path,
        evaluation_policy_path=settings.evaluation_policy_path,
        evaluation_report_schema_path=settings.evaluation_report_schema_path,
        expected_model_version=classifier.model_version,
        expected_artifact_sha256=classifier.checksum,
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
            event_factory=ResultEventFactory(model_evidence=model_evidence),
        ),
        validator=validator,
        storage=storage,
        publisher=publisher,
        classifier=classifier,
    )


@lru_cache
def get_runtime() -> WorkerRuntime:
    return build_runtime(get_settings())
