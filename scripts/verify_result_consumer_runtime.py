from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid5

import boto3
import pika
from sqlalchemy import create_engine, text

from reactorfront_api.result_consumer import (
    DOCUMENT_EXCHANGE,
    RESULT_QUEUE,
    RESULT_ROUTING_KEYS,
)
from reactorfront_api.settings import Settings
from pdf_fixture import build_fixture

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PROJECT_NAME = "reactorfront-portfolio"
ARTIFACT_DIRECTORY = REPOSITORY_ROOT / "artifacts" / "verification"
INVOICE_TEXT = REPOSITORY_ROOT / "tests" / "fixtures" / "canonical_invoice.txt"
REQUEST_QUEUE = "reactorfront.document-processing.requested.v1"
REQUEST_ROUTING_KEY = "document.processing.requested.v1"
MODEL_VERSION = "document-type-v1"


def compose(*arguments: str, capture: bool = False, check: bool = True) -> str:
    result = subprocess.run(
        ["docker", "compose", "-p", COMPOSE_PROJECT_NAME, *arguments],
        cwd=REPOSITORY_ROOT,
        check=check,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        text=capture,
    )
    return result.stdout.strip() if capture and result.stdout else ""


def broker_connection(settings: Settings) -> pika.BlockingConnection:
    parameters = pika.URLParameters(settings.rabbitmq_url.get_secret_value())
    parameters.connection_attempts = 1
    parameters.socket_timeout = 5
    parameters.stack_timeout = 5
    parameters.blocked_connection_timeout = 5
    return pika.BlockingConnection(parameters)


def prepare_queues(settings: Settings) -> None:
    connection = broker_connection(settings)
    try:
        channel = connection.channel()
        channel.exchange_declare(
            exchange=DOCUMENT_EXCHANGE,
            exchange_type="direct",
            durable=True,
        )
        channel.queue_declare(queue=REQUEST_QUEUE, durable=True)
        channel.queue_bind(
            queue=REQUEST_QUEUE,
            exchange=DOCUMENT_EXCHANGE,
            routing_key=REQUEST_ROUTING_KEY,
        )
        channel.queue_declare(queue=RESULT_QUEUE, durable=True)
        for routing_key in RESULT_ROUTING_KEYS:
            channel.queue_bind(
                queue=RESULT_QUEUE,
                exchange=DOCUMENT_EXCHANGE,
                routing_key=routing_key,
            )
        channel.queue_purge(queue=REQUEST_QUEUE)
        channel.queue_purge(queue=RESULT_QUEUE)
    finally:
        connection.close()


def submit_document(*, base_url: str, content: bytes, correlation_id: UUID) -> UUID:
    boundary = "reactorfront-result-consumer-boundary"
    body = (
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="invoice.pdf"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
        ).encode("ascii")
        + content
        + f"\r\n--{boundary}--\r\n".encode("ascii")
    )
    request = urllib.request.Request(
        f"{base_url}/api/v1/documents",
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
            "X-Correlation-ID": str(correlation_id),
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        value = json.loads(response.read())
    if response.status != 202 or value["status"] != "accepted":
        raise RuntimeError("Result-consumer verification submission was not accepted")
    return UUID(value["documentId"])


def get_status(*, base_url: str, document_id: UUID) -> dict[str, object]:
    with urllib.request.urlopen(
        f"{base_url}/api/v1/documents/{document_id}",
        timeout=5,
    ) as response:
        value = json.loads(response.read())
    if not isinstance(value, dict):
        raise RuntimeError("Document status was not a JSON object")
    return value


def wait_for_status(
    *,
    base_url: str,
    document_id: UUID,
    expected: str,
    timeout_seconds: float = 60,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    last_status = "unavailable"
    while time.monotonic() < deadline:
        try:
            value = get_status(base_url=base_url, document_id=document_id)
            last_status = str(value["status"])
            if last_status == expected:
                return value
        except OSError:
            last_status = "unavailable"
        time.sleep(0.25)
    raise RuntimeError(
        f"Document {document_id} did not reach {expected}; last status was {last_status}"
    )


def requested_payload(settings: Settings, *, document_id: UUID) -> dict[str, object]:
    engine = create_engine(settings.database_url)
    try:
        with engine.connect() as connection:
            payload = connection.execute(
                text(
                    "SELECT o.payload FROM outbox_events o "
                    "JOIN processing_jobs j ON j.id = o.aggregate_id "
                    "WHERE j.document_id = :document_id"
                ),
                {"document_id": document_id},
            ).scalar_one()
    finally:
        engine.dispose()
    if not isinstance(payload, dict):
        raise RuntimeError("Requested event payload was not stored as an object")
    return payload


def result_event(
    request: dict[str, object],
    *,
    event_type: str,
    source_sha256: str | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {
        "eventId": str(uuid5(UUID(str(request["eventId"])), event_type)),
        "eventType": event_type,
        "occurredAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "correlationId": str(request["correlationId"]),
        "documentId": str(request["documentId"]),
        "jobId": str(request["jobId"]),
        "objectKey": str(request["objectKey"]),
        "sourceSha256": source_sha256 or str(request["sourceSha256"]),
        "modelVersion": MODEL_VERSION,
    }
    if event_type == "document.processing.failed.v1":
        value["failureCode"] = "SOURCE_DIGEST_MISMATCH"
    return value


def publish_result(settings: Settings, payload: dict[str, object]) -> None:
    event_type = str(payload["eventType"])
    occurred_at = datetime.fromisoformat(str(payload["occurredAt"]))
    connection = broker_connection(settings)
    try:
        channel = connection.channel()
        channel.confirm_delivery()
        confirmed = channel.basic_publish(
            exchange=DOCUMENT_EXCHANGE,
            routing_key=event_type,
            body=json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(),
            properties=pika.BasicProperties(
                content_type="application/json",
                content_encoding="utf-8",
                delivery_mode=2,
                correlation_id=str(payload["correlationId"]),
                message_id=str(payload["eventId"]),
                timestamp=int(occurred_at.timestamp()),
                type=event_type,
                app_id="reactorfront-ml-worker",
                headers={
                    "correlationId": str(payload["correlationId"]),
                    "documentId": str(payload["documentId"]),
                    "jobId": str(payload["jobId"]),
                },
            ),
            mandatory=True,
        )
        if confirmed is False:
            raise RuntimeError("Injected result event was not broker-confirmed")
    finally:
        connection.close()


def publish_invalid_json(settings: Settings) -> None:
    connection = broker_connection(settings)
    try:
        channel = connection.channel()
        channel.confirm_delivery()
        confirmed = channel.basic_publish(
            exchange=DOCUMENT_EXCHANGE,
            routing_key="document.processing.started.v1",
            body=b"not-json",
            properties=pika.BasicProperties(
                content_type="application/json",
                content_encoding="utf-8",
                delivery_mode=2,
            ),
            mandatory=True,
        )
        if confirmed is False:
            raise RuntimeError("Injected poison event was not broker-confirmed")
    finally:
        connection.close()


def take_requested_message(settings: Settings) -> tuple[bytes, pika.BasicProperties]:
    deadline = time.monotonic() + 30
    connection = broker_connection(settings)
    try:
        channel = connection.channel()
        while time.monotonic() < deadline:
            method, properties, body = channel.basic_get(
                queue=REQUEST_QUEUE,
                auto_ack=False,
            )
            if method is None or properties is None or body is None:
                time.sleep(0.25)
                continue
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return body, properties
    finally:
        connection.close()
    raise RuntimeError("Timed out waiting for requested work")


def publish_requested_copies(
    settings: Settings,
    *,
    body: bytes,
    properties: pika.BasicProperties,
    copies: int,
) -> None:
    connection = broker_connection(settings)
    try:
        channel = connection.channel()
        channel.confirm_delivery()
        for _ in range(copies):
            confirmed = channel.basic_publish(
                exchange=DOCUMENT_EXCHANGE,
                routing_key=REQUEST_ROUTING_KEY,
                body=body,
                properties=properties,
                mandatory=True,
            )
            if confirmed is False:
                raise RuntimeError("Duplicate requested event was not confirmed")
    finally:
        connection.close()


def wait_for_queue_depth(settings: Settings, *, minimum: int) -> None:
    deadline = time.monotonic() + 60
    last_count = 0
    while time.monotonic() < deadline:
        connection = broker_connection(settings)
        try:
            declared = connection.channel().queue_declare(
                queue=RESULT_QUEUE, passive=True
            )
            last_count = declared.method.message_count
        finally:
            connection.close()
        if last_count >= minimum:
            return
        time.sleep(0.25)
    raise RuntimeError(f"Result queue depth stayed at {last_count}, expected {minimum}")


def wait_for_queue_empty(settings: Settings) -> None:
    deadline = time.monotonic() + 30
    last_count = -1
    while time.monotonic() < deadline:
        connection = broker_connection(settings)
        try:
            declared = connection.channel().queue_declare(
                queue=RESULT_QUEUE, passive=True
            )
            last_count = declared.method.message_count
        finally:
            connection.close()
        if last_count == 0:
            return
        time.sleep(0.25)
    raise RuntimeError(f"Result queue did not drain; last depth was {last_count}")


def wait_for_consumer_log(*, event: str, failure_code: str | None = None) -> None:
    deadline = time.monotonic() + 30
    expected_event = f'"event":"{event}"'
    expected_code = (
        f'"failure_code":"{failure_code}"' if failure_code is not None else None
    )
    while time.monotonic() < deadline:
        logs = compose("logs", "--no-color", "api-events", capture=True)
        if expected_event in logs and (expected_code is None or expected_code in logs):
            return
        time.sleep(0.25)
    raise RuntimeError(f"API event consumer did not log {event}/{failure_code}")


def persistence_evidence(settings: Settings, *, document_id: UUID) -> dict[str, object]:
    engine = create_engine(settings.database_url)
    try:
        with engine.connect() as connection:
            job = (
                connection.execute(
                    text(
                        "SELECT j.id, j.status, j.attempt_count, j.model_version, "
                        "j.predicted_class, j.confidence, j.failure_code, "
                        "j.started_at, j.completed_at "
                        "FROM processing_jobs j WHERE j.document_id = :document_id"
                    ),
                    {"document_id": document_id},
                )
                .mappings()
                .one()
            )
            receipts = (
                connection.execute(
                    text(
                        "SELECT r.event_type, r.logical_payload_sha256 "
                        "FROM result_event_receipts r "
                        "WHERE r.document_id = :document_id ORDER BY r.event_type"
                    ),
                    {"document_id": document_id},
                )
                .mappings()
                .all()
            )
    finally:
        engine.dispose()
    return {
        "jobId": str(job["id"]),
        "status": job["status"],
        "attemptCount": job["attempt_count"],
        "modelVersion": job["model_version"],
        "classification": job["predicted_class"],
        "confidence": float(job["confidence"])
        if job["confidence"] is not None
        else None,
        "failureCode": job["failure_code"],
        "startedAt": job["started_at"].isoformat() if job["started_at"] else None,
        "completedAt": job["completed_at"].isoformat() if job["completed_at"] else None,
        "receipts": [dict(receipt) for receipt in receipts],
    }


def overwrite_source(settings: Settings, *, object_key: str) -> None:
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
        region_name=settings.s3_region,
    )
    client.put_object(
        Bucket=settings.s3_bucket,
        Key=object_key,
        Body=b"tampered after accepted digest",
        ContentType="application/pdf",
    )


def main() -> int:
    settings = Settings()
    base_url = os.environ.get("PORTFOLIO_API_BASE_URL", "http://127.0.0.1:58000")
    invoice_pdf = build_fixture(INVOICE_TEXT)

    compose("stop", "api-events", "ml-worker", "api-outbox")
    prepare_queues(settings)
    compose("up", "--detach", "--build", "--wait", "api-events")

    success_document = submit_document(
        base_url=base_url,
        content=invoice_pdf,
        correlation_id=UUID("cccccccc-cccc-4ccc-8ccc-ccccccccccc1"),
    )
    success_request = requested_payload(settings, document_id=success_document)
    publish_result(
        settings,
        result_event(
            success_request,
            event_type="document.processing.started.v1",
        ),
    )
    wait_for_consumer_log(event="result_event_deferred")

    compose("up", "--detach", "--wait", "api-outbox")
    processing = wait_for_status(
        base_url=base_url,
        document_id=success_document,
        expected="processing",
    )
    requested_body, requested_properties = take_requested_message(settings)
    publish_requested_copies(
        settings,
        body=requested_body,
        properties=requested_properties,
        copies=2,
    )

    compose("stop", "api-events")
    compose("up", "--detach", "--build", "--wait", "ml-worker")
    wait_for_queue_depth(settings, minimum=4)
    compose("restart", "rabbitmq")
    compose(
        "up",
        "--detach",
        "--wait",
        "rabbitmq",
        "api",
        "api-outbox",
        "ml-worker",
    )
    compose("up", "--detach", "--wait", "api-events")
    completed = wait_for_status(
        base_url=base_url,
        document_id=success_document,
        expected="completed",
    )
    success_persistence = persistence_evidence(
        settings,
        document_id=success_document,
    )
    success_receipt_types = {
        receipt["event_type"] for receipt in success_persistence["receipts"]
    }
    if (
        completed.get("classification") != "invoice"
        or float(completed.get("confidence", 0)) < 0.70
        or completed.get("modelVersion") != MODEL_VERSION
        or not completed.get("startedAt")
        or not completed.get("completedAt")
        or success_persistence["status"] != "completed"
        or success_persistence["attemptCount"] != 1
        or success_persistence["modelVersion"] != MODEL_VERSION
        or success_persistence["classification"] != "invoice"
        or success_persistence["failureCode"] is not None
        or not success_persistence["startedAt"]
        or not success_persistence["completedAt"]
        or success_receipt_types
        != {
            "document.processing.started.v1",
            "document.processing.completed.v1",
        }
    ):
        raise RuntimeError("Completed API-owned result persistence was inconsistent")

    wrong_failed = result_event(
        success_request,
        event_type="document.processing.failed.v1",
        source_sha256="f" * 64,
    )
    publish_result(settings, wrong_failed)
    wait_for_consumer_log(
        event="result_event_rejected",
        failure_code="IDENTITY_MISMATCH",
    )
    publish_result(
        settings,
        result_event(
            success_request,
            event_type="document.processing.failed.v1",
        ),
    )
    wait_for_consumer_log(
        event="result_event_rejected",
        failure_code="TERMINAL_CONFLICT",
    )
    publish_invalid_json(settings)
    wait_for_consumer_log(
        event="result_event_rejected",
        failure_code="INVALID_EVENT",
    )
    wait_for_queue_empty(settings)
    if get_status(base_url=base_url, document_id=success_document) != completed:
        raise RuntimeError("Rejected result events changed the first terminal result")

    compose("stop", "api-events", "ml-worker")
    prepare_queues(settings)
    compose("up", "--detach", "--wait", "api-events", "api-outbox")
    failed_document = submit_document(
        base_url=base_url,
        content=invoice_pdf,
        correlation_id=UUID("cccccccc-cccc-4ccc-8ccc-ccccccccccc2"),
    )
    wait_for_status(
        base_url=base_url,
        document_id=failed_document,
        expected="queued",
    )
    failed_request = requested_payload(settings, document_id=failed_document)
    failed_body, failed_properties = take_requested_message(settings)
    overwrite_source(settings, object_key=str(failed_request["objectKey"]))
    publish_requested_copies(
        settings,
        body=failed_body,
        properties=failed_properties,
        copies=1,
    )
    compose("up", "--detach", "--wait", "ml-worker")
    failed = wait_for_status(
        base_url=base_url,
        document_id=failed_document,
        expected="failed",
    )
    failed_persistence = persistence_evidence(
        settings,
        document_id=failed_document,
    )
    failed_receipt_types = {
        receipt["event_type"] for receipt in failed_persistence["receipts"]
    }
    if (
        failed.get("failureCode") != "SOURCE_DIGEST_MISMATCH"
        or failed.get("classification") is not None
        or failed.get("confidence") is not None
        or failed_persistence["status"] != "failed"
        or failed_persistence["attemptCount"] != 1
        or failed_persistence["modelVersion"] != MODEL_VERSION
        or failed_persistence["classification"] is not None
        or failed_persistence["confidence"] is not None
        or failed_persistence["failureCode"] != "SOURCE_DIGEST_MISMATCH"
        or not failed_persistence["startedAt"]
        or not failed_persistence["completedAt"]
        or failed_receipt_types
        != {
            "document.processing.started.v1",
            "document.processing.failed.v1",
        }
    ):
        raise RuntimeError("Failed API-owned result persistence was inconsistent")

    compose("stop", "rabbitmq")
    failed_probe = subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            COMPOSE_PROJECT_NAME,
            "exec",
            "-T",
            "api-events",
            "python",
            "-m",
            "reactorfront_api.events_main",
            "--check",
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if failed_probe.returncode == 0:
        raise RuntimeError(
            "API event-consumer readiness stayed positive without RabbitMQ"
        )
    compose("up", "--detach", "--wait", "rabbitmq", "api", "api-outbox", "api-events")

    proof = {
        "processingStatus": processing["status"],
        "completed": completed,
        "completedPersistence": success_persistence,
        "failed": failed,
        "failedPersistence": failed_persistence,
        "outboxFinalizeRaceRecovered": True,
        "duplicateLogicalEventsDeduplicated": True,
        "brokerRestartPersistence": True,
        "consumerRestartRecovery": True,
        "identityMismatchRejected": True,
        "terminalConflictRejected": True,
        "invalidEventRejected": True,
        "dependencyReadinessRecovery": True,
        "invoiceSha256": hashlib.sha256(invoice_pdf).hexdigest(),
    }
    ARTIFACT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIRECTORY / "api-events-runtime-proof.json").write_text(
        json.dumps(proof, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(proof, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
