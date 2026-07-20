from __future__ import annotations

from dataclasses import dataclass

import pytest

import reactorfront_api.events_main as events_main
from reactorfront_api.settings import Settings


@dataclass
class FakeConsumer:
    ready: bool = True
    ran: bool = False
    closed: bool = False

    def is_ready(self) -> bool:
        return self.ready

    def run_forever(self, _stop_event: object) -> None:
        self.ran = True

    def close(self) -> None:
        self.closed = True


def test_build_consumer_uses_api_owned_settings() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:password@database/events",
        rabbitmq_url="amqp://user:password@broker/%2F",
        rabbitmq_timeout_seconds=4,
        events_prefetch_count=2,
        events_requeue_delay_seconds=0.5,
        events_reconnect_delay_seconds=2,
    )

    consumer = events_main.build_consumer(settings)

    assert consumer._timeout_seconds == 4
    assert consumer._prefetch_count == 2
    assert consumer._requeue_delay_seconds == 0.5
    assert consumer._reconnect_delay_seconds == 2
    consumer.close()


@pytest.mark.parametrize(("ready", "expected"), [(True, 0), (False, 1)])
def test_main_check_returns_readiness_and_closes(
    monkeypatch: pytest.MonkeyPatch,
    ready: bool,
    expected: int,
) -> None:
    consumer = FakeConsumer(ready=ready)
    monkeypatch.setattr(events_main, "build_consumer", lambda _settings: consumer)
    monkeypatch.setattr(events_main, "parse_args", lambda: type("Args", (), {"check": True})())

    assert events_main.main() == expected
    assert consumer.closed
    assert not consumer.ran


def test_main_runs_consumer_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    consumer = FakeConsumer()
    monkeypatch.setattr(events_main, "build_consumer", lambda _settings: consumer)
    monkeypatch.setattr(events_main, "parse_args", lambda: type("Args", (), {"check": False})())
    monkeypatch.setattr(events_main.signal, "signal", lambda *_values: None)

    assert events_main.main() == 0
    assert consumer.ran
    assert consumer.closed
