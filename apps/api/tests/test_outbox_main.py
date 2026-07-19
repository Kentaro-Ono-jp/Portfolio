from __future__ import annotations

import argparse
from dataclasses import dataclass
from threading import Event

import pytest

import reactorfront_api.outbox_main as outbox_main
from reactorfront_api.settings import Settings


@dataclass
class FakeDispatcher:
    ready: bool = True
    ran: bool = False
    closed: bool = False

    def is_ready(self) -> bool:
        return self.ready

    def run_forever(self, stop_event: Event) -> None:
        self.ran = True
        stop_event.set()

    def close(self) -> None:
        self.closed = True


def test_build_dispatcher_uses_safe_settings() -> None:
    settings = Settings(
        outbox_batch_size=4,
        outbox_lease_seconds=20,
        outbox_poll_seconds=0.5,
        outbox_retry_base_seconds=2,
        outbox_retry_max_seconds=10,
    )
    dispatcher = outbox_main.build_dispatcher(settings, lease_owner="test-owner")
    try:
        assert dispatcher._lease_owner == "test-owner"
        assert dispatcher._policy.batch_size == 4
        assert dispatcher._policy.lease_duration.total_seconds() == 20
        assert dispatcher._policy.retry_base_seconds == 2
    finally:
        dispatcher.close()


@pytest.mark.parametrize(("ready", "expected"), [(True, 0), (False, 1)])
def test_check_mode_returns_readiness_and_closes(
    monkeypatch: pytest.MonkeyPatch,
    ready: bool,
    expected: int,
) -> None:
    dispatcher = FakeDispatcher(ready=ready)
    monkeypatch.setattr(outbox_main, "build_dispatcher", lambda _settings: dispatcher)
    monkeypatch.setattr(outbox_main, "parse_args", lambda: argparse.Namespace(check=True))

    assert outbox_main.main() == expected
    assert dispatcher.closed


def test_runtime_mode_registers_signals_and_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatcher = FakeDispatcher()
    registered: list[int] = []
    monkeypatch.setattr(outbox_main, "build_dispatcher", lambda _settings: dispatcher)
    monkeypatch.setattr(outbox_main, "parse_args", lambda: argparse.Namespace(check=False))
    monkeypatch.setattr(
        outbox_main.signal,
        "signal",
        lambda signal_number, _handler: registered.append(signal_number),
    )

    assert outbox_main.main() == 0
    assert dispatcher.ran
    assert dispatcher.closed
    assert registered == [outbox_main.signal.SIGTERM, outbox_main.signal.SIGINT]
