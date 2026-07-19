from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import httpx2 as httpx
import pika
from sqlalchemy import create_engine, text

from reactorfront_api.persistence import SqlAlchemyOutboxRepository
from reactorfront_api.rabbitmq import REQUEST_QUEUE, REQUEST_TASK_NAME
from reactorfront_api.settings import Settings

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PROJECT_NAME = "reactorfront-portfolio"
PDF = b"%PDF-1.7\nReactorFront outbox recovery proof"
CORRELATION_IDS = (
    UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1"),
    UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2"),
)


def compose(*arguments: str) -> None:
    subprocess.run(
        ["docker", "compose", "-p", COMPOSE_PROJECT_NAME, *arguments],
        cwd=REPOSITORY_ROOT,
        check=True,
    )


def submit_document(*, base_url: str, correlation_id: UUID) -> tuple[UUID, UUID]:
    with httpx.Client(base_url=base_url, timeout=10) as client:
        response = client.post(
            "/api/v1/documents",
            files={"file": ("invoice.pdf", PDF, "application/pdf")},
            headers={"X-Correlation-ID": str(correlation_id)},
        )
    response.raise_for_status()
    body = response.json()
    if body["status"] != "accepted":
        raise RuntimeError("Submitted document did not start in accepted state")
    return UUID(body["documentId"]), UUID(body["jobId"])


def wait_for_status(*, base_url: str, document_id: UUID, expected: str) -> None:
    deadline = time.monotonic() + 30
    last_status = "unavailable"
    while time.monotonic() < deadline:
        try:
            with httpx.Client(base_url=base_url, timeout=5) as client:
                response = client.get(f"/api/v1/documents/{document_id}")
            if response.is_success:
                last_status = str(response.json()["status"])
                if last_status == expected:
                    return
        except httpx.HTTPError:
            last_status = "unavailable"
        time.sleep(0.25)
    raise RuntimeError(
        f"Document {document_id} did not reach {expected}; last status was {last_status}"
    )


def event_id_for_job(*, database_url: str, job_id: UUID) -> UUID:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            value = connection.execute(
                text("SELECT event_id FROM outbox_events WHERE aggregate_id = :job_id"),
                {"job_id": job_id},
            ).scalar_one()
        return UUID(str(value))
    finally:
        engine.dispose()


def create_expired_crash_lease(*, database_url: str, event_id: UUID) -> None:
    engine = create_engine(database_url)
    repository = SqlAlchemyOutboxRepository(engine=engine)
    try:
        leased = repository.lease_pending(
            lease_owner="simulated-crashed-dispatcher",
            lease_duration=timedelta(seconds=60),
            batch_size=1,
        )
        if len(leased) != 1 or leased[0].event_id != event_id:
            raise RuntimeError(
                "Could not create the simulated crashed-dispatcher lease"
            )
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE outbox_events "
                    "SET leased_until = CURRENT_TIMESTAMP - INTERVAL '1 second' "
                    "WHERE event_id = :event_id"
                ),
                {"event_id": event_id},
            )
    finally:
        repository.close()


def purge_requested_queue(settings: Settings) -> None:
    connection = pika.BlockingConnection(
        pika.URLParameters(settings.rabbitmq_url.get_secret_value())
    )
    try:
        channel = connection.channel()
        channel.queue_declare(queue=REQUEST_QUEUE, durable=True)
        channel.queue_purge(queue=REQUEST_QUEUE)
    finally:
        connection.close()


def consume_requested_events(
    settings: Settings,
    *,
    expected_event_ids: set[UUID],
) -> None:
    connection = pika.BlockingConnection(
        pika.URLParameters(settings.rabbitmq_url.get_secret_value())
    )
    observed: set[UUID] = set()
    try:
        channel = connection.channel()
        deadline = time.monotonic() + 15
        while observed != expected_event_ids and time.monotonic() < deadline:
            method, properties, body = channel.basic_get(
                queue=REQUEST_QUEUE,
                auto_ack=False,
            )
            if method is None or properties is None or body is None:
                time.sleep(0.25)
                continue
            event_id = UUID(str(properties.message_id))
            task_body = json.loads(body)
            payload = task_body[0][0]
            if properties.delivery_mode != 2:
                raise RuntimeError("Requested message is not persistent")
            if properties.headers["task"] != REQUEST_TASK_NAME:
                raise RuntimeError(
                    "Requested message is not Celery protocol compatible"
                )
            if UUID(payload["eventId"]) != event_id:
                raise RuntimeError(
                    "Broker message identity does not match its event payload"
                )
            observed.add(event_id)
            channel.basic_ack(delivery_tag=method.delivery_tag)
    finally:
        connection.close()
    if observed != expected_event_ids:
        raise RuntimeError(
            f"Expected persistent events {expected_event_ids}, observed {observed}"
        )


def main() -> int:
    settings = Settings()
    base_url = os.environ.get("PORTFOLIO_API_BASE_URL", "http://127.0.0.1:58000")
    database_url = settings.database_url

    compose("stop", "api-outbox")
    purge_requested_queue(settings)

    first_document, first_job = submit_document(
        base_url=base_url,
        correlation_id=CORRELATION_IDS[0],
    )
    first_event = event_id_for_job(database_url=database_url, job_id=first_job)
    create_expired_crash_lease(database_url=database_url, event_id=first_event)

    compose("up", "--detach", "--wait", "api-outbox")
    wait_for_status(base_url=base_url, document_id=first_document, expected="queued")

    compose("stop", "api-outbox")
    second_document, second_job = submit_document(
        base_url=base_url,
        correlation_id=CORRELATION_IDS[1],
    )
    second_event = event_id_for_job(database_url=database_url, job_id=second_job)

    compose("restart", "rabbitmq")
    compose("up", "--detach", "--wait", "rabbitmq", "api")
    compose("up", "--detach", "--wait", "api-outbox")
    wait_for_status(base_url=base_url, document_id=second_document, expected="queued")

    consume_requested_events(
        settings,
        expected_event_ids={first_event, second_event},
    )
    print("Outbox restart, broker persistence, and queued-state recovery passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
