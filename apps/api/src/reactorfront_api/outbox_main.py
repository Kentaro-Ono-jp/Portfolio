from __future__ import annotations

import argparse
import logging
import signal
import socket
from datetime import timedelta
from threading import Event

from reactorfront_api.outbox import DispatcherPolicy, OutboxDispatcher
from reactorfront_api.persistence import SqlAlchemyOutboxRepository, create_database_engine
from reactorfront_api.rabbitmq import PikaOutboxPublisher
from reactorfront_api.settings import Settings, get_settings


def build_dispatcher(settings: Settings, *, lease_owner: str | None = None) -> OutboxDispatcher:
    repository = SqlAlchemyOutboxRepository(engine=create_database_engine(settings.database_url))
    publisher = PikaOutboxPublisher(
        broker_url=settings.rabbitmq_url.get_secret_value(),
        timeout_seconds=settings.rabbitmq_timeout_seconds,
    )
    policy = DispatcherPolicy(
        batch_size=settings.outbox_batch_size,
        lease_duration=timedelta(seconds=settings.outbox_lease_seconds),
        poll_seconds=settings.outbox_poll_seconds,
        retry_base_seconds=settings.outbox_retry_base_seconds,
        retry_max_seconds=settings.outbox_retry_max_seconds,
    )
    return OutboxDispatcher(
        repository=repository,
        publisher=publisher,
        lease_owner=lease_owner or socket.gethostname(),
        policy=policy,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the API-owned outbox dispatcher.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit successfully only when PostgreSQL and RabbitMQ are ready.",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    dispatcher = build_dispatcher(get_settings())
    try:
        if parse_args().check:
            return 0 if dispatcher.is_ready() else 1

        stop_event = Event()

        def request_stop(_signum: int, _frame: object) -> None:
            stop_event.set()

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
        dispatcher.run_forever(stop_event)
        return 0
    finally:
        dispatcher.close()


if __name__ == "__main__":
    raise SystemExit(main())
