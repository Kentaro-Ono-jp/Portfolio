from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import boto3
import pika

from reactorfront_ml.event_contracts import JsonSchemaEventValidator
from reactorfront_ml.events import (
    COMPLETED_EVENT_TYPE,
    FAILED_EVENT_TYPE,
    RESULT_EVENT_TYPES,
    STARTED_EVENT_TYPE,
)
from reactorfront_ml.rabbitmq import (
    DOCUMENT_EXCHANGE,
    REQUEST_QUEUE,
    REQUEST_ROUTING_KEY,
    RESULT_QUEUE,
)
from reactorfront_ml.model import MODEL_VERSION
from reactorfront_ml.settings import Settings
from pdf_fixture import build_fixture

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PROJECT_NAME = "reactorfront-portfolio"
EXPECTED_MODEL_CHECKSUM = (
    (REPOSITORY_ROOT / "apps" / "ml" / "model.expected.sha256")
    .read_text(encoding="utf-8")
    .strip()
)
INVOICE_TEXT = REPOSITORY_ROOT / "tests" / "fixtures" / "canonical_invoice.txt"
ARTIFACT_DIRECTORY = REPOSITORY_ROOT / "artifacts" / "verification"
CORRELATION_IDS = (
    UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1"),
    UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2"),
)


@dataclass(frozen=True, slots=True)
class RequestedMessage:
    body: bytes
    properties: pika.BasicProperties
    payload: dict[str, object]


def compose(*arguments: str, capture: bool = False) -> str:
    result = subprocess.run(
        ["docker", "compose", "-p", COMPOSE_PROJECT_NAME, *arguments],
        cwd=REPOSITORY_ROOT,
        check=True,
        stdout=subprocess.PIPE if capture else None,
        text=capture,
    )
    return result.stdout.strip() if capture and result.stdout else ""


def compose_succeeds(*arguments: str) -> bool:
    result = subprocess.run(
        ["docker", "compose", "-p", COMPOSE_PROJECT_NAME, *arguments],
        cwd=REPOSITORY_ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def broker_connection(settings: Settings) -> pika.BlockingConnection:
    parameters = pika.URLParameters(settings.rabbitmq_url.get_secret_value())
    parameters.connection_attempts = 1
    parameters.socket_timeout = 5
    parameters.stack_timeout = 5
    parameters.blocked_connection_timeout = 5
    return pika.BlockingConnection(parameters)


def prepare_queues(settings: Settings, *, purge_requested: bool = True) -> None:
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
        for event_type in RESULT_EVENT_TYPES:
            channel.queue_bind(
                queue=RESULT_QUEUE,
                exchange=DOCUMENT_EXCHANGE,
                routing_key=event_type,
            )
        if purge_requested:
            channel.queue_purge(queue=REQUEST_QUEUE)
        channel.queue_purge(queue=RESULT_QUEUE)
    finally:
        connection.close()


def submit_document(*, base_url: str, content: bytes, correlation_id: UUID) -> UUID:
    boundary = "reactorfront-portfolio-boundary"
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
        raise RuntimeError("Canonical ML submission was not accepted")
    return UUID(value["documentId"])


def wait_for_status(*, base_url: str, document_id: UUID, expected: str) -> None:
    deadline = time.monotonic() + 30
    last_status = "unavailable"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                f"{base_url}/api/v1/documents/{document_id}", timeout=5
            ) as response:
                value = json.loads(response.read())
            last_status = str(value["status"])
            if last_status == expected:
                return
        except OSError:
            last_status = "unavailable"
        time.sleep(0.25)
    raise RuntimeError(
        f"Document {document_id} did not reach {expected}; last status was {last_status}"
    )


def take_requested_message(settings: Settings) -> RequestedMessage:
    deadline = time.monotonic() + 20
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
            value = json.loads(body)
            payload = value[0][0]
            if not isinstance(payload, dict):
                raise RuntimeError(
                    "Requested Celery message did not carry an event object"
                )
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return RequestedMessage(body=body, properties=properties, payload=payload)
    finally:
        connection.close()
    raise RuntimeError("Timed out waiting for requested message")


def publish_requested_duplicates(
    settings: Settings,
    *,
    message: RequestedMessage,
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
                body=message.body,
                properties=message.properties,
                mandatory=True,
            )
            if confirmed is False:
                raise RuntimeError("Duplicate requested message was not confirmed")
    finally:
        connection.close()


def requeue_requested_message(settings: Settings, message: RequestedMessage) -> None:
    publish_requested_duplicates(settings, message=message, copies=1)


def wait_for_result_depth(settings: Settings, *, minimum: int) -> None:
    deadline = time.monotonic() + 60
    last_count = 0
    while time.monotonic() < deadline:
        connection = broker_connection(settings)
        try:
            method = connection.channel().queue_declare(
                queue=RESULT_QUEUE, passive=True
            )
            last_count = method.method.message_count
        finally:
            connection.close()
        if last_count >= minimum:
            return
        time.sleep(0.25)
    raise RuntimeError(f"Result queue depth stayed at {last_count}, expected {minimum}")


def consume_results(
    settings: Settings,
    *,
    expected_count: int,
) -> list[dict[str, object]]:
    validator = JsonSchemaEventValidator(
        contract_directory=settings.event_contract_directory
    )
    deadline = time.monotonic() + 30
    observed: list[dict[str, object]] = []
    connection = broker_connection(settings)
    try:
        channel = connection.channel()
        while len(observed) < expected_count and time.monotonic() < deadline:
            method, properties, body = channel.basic_get(
                queue=RESULT_QUEUE,
                auto_ack=False,
            )
            if method is None or properties is None or body is None:
                time.sleep(0.25)
                continue
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise RuntimeError("Result message was not a JSON object")
            event_type = str(payload.get("eventType"))
            validator.validate(event_type=event_type, payload=payload)
            if (
                properties.delivery_mode != 2
                or properties.message_id != payload["eventId"]
            ):
                raise RuntimeError("Result message persistence or identity is invalid")
            if properties.correlation_id != payload["correlationId"]:
                raise RuntimeError("Result correlation identity is invalid")
            if (
                properties.type != event_type
                or properties.content_type != "application/json"
            ):
                raise RuntimeError(
                    "Result message type or encoding metadata is invalid"
                )
            observed.append(payload)
            channel.basic_ack(delivery_tag=method.delivery_tag)
    finally:
        connection.close()
    if len(observed) != expected_count:
        raise RuntimeError(
            f"Expected {expected_count} result events, got {len(observed)}"
        )
    return observed


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


def assert_preserved_identifiers(
    events: list[dict[str, object]],
    *,
    request: RequestedMessage,
) -> None:
    for field in (
        "correlationId",
        "documentId",
        "jobId",
        "objectKey",
        "sourceSha256",
    ):
        if any(event[field] != request.payload[field] for event in events):
            raise RuntimeError(f"Result events did not preserve {field}")


def assert_success_events(events: list[dict[str, object]]) -> dict[str, object]:
    started = [event for event in events if event["eventType"] == STARTED_EVENT_TYPE]
    completed = [
        event for event in events if event["eventType"] == COMPLETED_EVENT_TYPE
    ]
    if len(started) != 2 or len(completed) != 2:
        raise RuntimeError(
            "Duplicate delivery did not produce two complete event pairs"
        )
    if len({event["eventId"] for event in started}) != 1:
        raise RuntimeError("Duplicate started events did not preserve logical identity")
    if len({event["eventId"] for event in completed}) != 1:
        raise RuntimeError(
            "Duplicate completed events did not preserve logical identity"
        )
    normalized_completed = [
        {key: value for key, value in event.items() if key != "occurredAt"}
        for event in completed
    ]
    if normalized_completed[0] != normalized_completed[1]:
        raise RuntimeError("Duplicate delivery produced inconsistent logical results")
    terminal = completed[0]
    if terminal["classification"] != "invoice" or float(terminal["confidence"]) < 0.70:
        raise RuntimeError("Real PDF/PyTorch invoice result did not meet its contract")
    if any(event["modelVersion"] != MODEL_VERSION for event in events):
        raise RuntimeError(
            "Result event model version did not match the reviewed model"
        )
    return terminal


def assert_failure_events(events: list[dict[str, object]]) -> dict[str, object]:
    types = [event["eventType"] for event in events]
    if types != [STARTED_EVENT_TYPE, FAILED_EVENT_TYPE]:
        raise RuntimeError(f"Digest failure event order was unexpected: {types}")
    failed = events[-1]
    if failed["failureCode"] != "SOURCE_DIGEST_MISMATCH":
        raise RuntimeError("Digest failure did not use its stable sanitized code")
    if any(event["modelVersion"] != MODEL_VERSION for event in events):
        raise RuntimeError(
            "Failure event model version did not match the reviewed model"
        )
    return failed


def inspect_worker_boundary() -> dict[str, object]:
    probe = (
        "import importlib.util,json,os,torch; "
        "forbidden=sorted(k for k in os.environ "
        "if 'DATABASE' in k.upper() or 'POSTGRES' in k.upper()); "
        "drivers=[n for n in ('psycopg','sqlalchemy') "
        "if importlib.util.find_spec(n) is not None]; "
        "print(json.dumps({'uid':os.getuid(),'forbidden':forbidden,'drivers':drivers,"
        "'cudaVersion':torch.version.cuda,'cudaAvailable':torch.cuda.is_available()}))"
    )
    value = json.loads(
        compose("exec", "-T", "ml-worker", "python", "-c", probe, capture=True)
    )
    if value != {
        "uid": 10002,
        "forbidden": [],
        "drivers": [],
        "cudaVersion": None,
        "cudaAvailable": False,
    }:
        raise RuntimeError(f"ML image runtime boundary was invalid: {value}")
    return value


def prove_dependency_readiness_recovery(service: str) -> None:
    compose("stop", service)
    if compose_succeeds(
        "exec",
        "-T",
        "ml-worker",
        "python",
        "-m",
        "reactorfront_ml.health",
        "--check",
    ):
        raise RuntimeError(f"ML readiness stayed positive while {service} was stopped")
    compose("up", "--detach", "--wait", service, "ml-worker")


def main() -> int:
    settings = Settings()
    base_url = os.environ.get("PORTFOLIO_API_BASE_URL", "http://127.0.0.1:58000")
    invoice_pdf = build_fixture(INVOICE_TEXT)

    compose("stop", "ml-worker", "api-outbox")
    prepare_queues(settings)
    compose("up", "--detach", "--wait", "api-outbox")

    success_document = submit_document(
        base_url=base_url,
        content=invoice_pdf,
        correlation_id=CORRELATION_IDS[0],
    )
    wait_for_status(base_url=base_url, document_id=success_document, expected="queued")
    success_request = take_requested_message(settings)
    publish_requested_duplicates(settings, message=success_request, copies=2)

    compose("up", "--detach", "--build", "--wait", "ml-worker")
    worker_boundary = inspect_worker_boundary()
    wait_for_result_depth(settings, minimum=4)
    compose("restart", "rabbitmq")
    compose("up", "--detach", "--wait", "rabbitmq", "api", "api-outbox", "ml-worker")
    success_events = consume_results(settings, expected_count=4)
    assert_preserved_identifiers(success_events, request=success_request)
    completed = assert_success_events(success_events)
    wait_for_status(base_url=base_url, document_id=success_document, expected="queued")

    image_checksum = compose(
        "exec",
        "-T",
        "ml-worker",
        "cat",
        "/opt/reactorfront/model/model.sha256",
        capture=True,
    )
    if image_checksum != EXPECTED_MODEL_CHECKSUM:
        raise RuntimeError("ML image model checksum does not match reviewed metadata")

    compose("stop", "ml-worker")
    prepare_queues(settings)
    failure_document = submit_document(
        base_url=base_url,
        content=invoice_pdf,
        correlation_id=CORRELATION_IDS[1],
    )
    wait_for_status(base_url=base_url, document_id=failure_document, expected="queued")
    failure_request = take_requested_message(settings)
    overwrite_source(settings, object_key=str(failure_request.payload["objectKey"]))
    requeue_requested_message(settings, failure_request)
    compose("up", "--detach", "--wait", "ml-worker")
    failure_events = consume_results(settings, expected_count=2)
    assert_preserved_identifiers(failure_events, request=failure_request)
    failed = assert_failure_events(failure_events)
    wait_for_status(base_url=base_url, document_id=failure_document, expected="queued")

    prove_dependency_readiness_recovery("minio")
    prove_dependency_readiness_recovery("rabbitmq")

    ARTIFACT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    proof = {
        "modelSha256": image_checksum,
        "classification": completed["classification"],
        "confidence": completed["confidence"],
        "modelVersion": completed["modelVersion"],
        "duplicateStartedEventId": next(
            event["eventId"]
            for event in success_events
            if event["eventType"] == STARTED_EVENT_TYPE
        ),
        "duplicateCompletedEventId": completed["eventId"],
        "failureCode": failed["failureCode"],
        "containerUid": worker_boundary["uid"],
        "databaseCredentialPresent": bool(worker_boundary["forbidden"]),
        "databaseDriverPresent": bool(worker_boundary["drivers"]),
        "cudaVersion": worker_boundary["cudaVersion"],
        "cudaAvailable": worker_boundary["cudaAvailable"],
        "brokerRestartPersistence": True,
        "workerRestartRecovery": True,
        "dependencyReadinessRecovery": True,
    }
    (ARTIFACT_DIRECTORY / "ml-runtime-proof.json").write_text(
        json.dumps(proof, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(proof, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
