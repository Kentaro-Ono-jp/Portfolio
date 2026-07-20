from __future__ import annotations

import argparse
import logging
import signal
from threading import Event

from reactorfront_api.event_contracts import JsonSchemaEventValidator
from reactorfront_api.persistence import (
    SqlAlchemyResultEventRepository,
    create_database_engine,
)
from reactorfront_api.result_consumer import (
    PikaResultEventConsumer,
    ResultEventMessageHandler,
)
from reactorfront_api.settings import Settings, get_settings


def build_consumer(settings: Settings) -> PikaResultEventConsumer:
    repository = SqlAlchemyResultEventRepository(
        engine=create_database_engine(settings.database_url)
    )
    handler = ResultEventMessageHandler(
        repository=repository,
        validator=JsonSchemaEventValidator(contract_directory=settings.event_contract_directory),
    )
    return PikaResultEventConsumer(
        broker_url=settings.rabbitmq_url.get_secret_value(),
        timeout_seconds=settings.rabbitmq_timeout_seconds,
        prefetch_count=settings.events_prefetch_count,
        requeue_delay_seconds=settings.events_requeue_delay_seconds,
        reconnect_delay_seconds=settings.events_reconnect_delay_seconds,
        handler=handler,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the API-owned result-event consumer.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit successfully only when PostgreSQL and RabbitMQ are ready.",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    consumer = build_consumer(get_settings())
    try:
        if parse_args().check:
            return 0 if consumer.is_ready() else 1

        stop_event = Event()

        def request_stop(_signum: int, _frame: object) -> None:
            stop_event.set()

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
        consumer.run_forever(stop_event)
        return 0
    finally:
        consumer.close()


if __name__ == "__main__":
    raise SystemExit(main())
