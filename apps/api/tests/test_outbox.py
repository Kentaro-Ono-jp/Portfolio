from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import UUID

import pytest

from reactorfront_api.domain import (
    OutboxInvariantError,
    OutboxLease,
    OutboxPublishError,
    PublishFailureCode,
    PublishFinalizeResult,
)
from reactorfront_api.outbox import (
    DispatchCycleResult,
    DispatcherPolicy,
    OutboxDispatcher,
)

EVENT_ID = UUID("44444444-4444-4444-8444-444444444444")
JOB_ID = UUID("33333333-3333-4333-8333-333333333333")
CORRELATION_ID = UUID("11111111-1111-4111-8111-111111111111")
NOW = datetime(2026, 7, 19, 0, 0, tzinfo=UTC)


def leased_event(*, attempt_count: int = 1) -> OutboxLease:
    return OutboxLease(
        event_id=EVENT_ID,
        event_type="document.processing.requested.v1",
        job_id=JOB_ID,
        payload={
            "eventId": str(EVENT_ID),
            "correlationId": str(CORRELATION_ID),
        },
        created_at=NOW,
        lease_owner="dispatcher-a",
        leased_until=NOW + timedelta(seconds=30),
        attempt_count=attempt_count,
    )


@dataclass
class FakeOutboxRepository:
    leases: list[OutboxLease] = field(default_factory=list)
    finalize_result: PublishFinalizeResult = PublishFinalizeResult.PUBLISHED
    lease_error: Exception | None = None
    finalize_error: Exception | None = None
    failure_error: Exception | None = None
    ready: bool = True
    leased_requests: list[tuple[str, timedelta, int]] = field(default_factory=list)
    finalized: list[tuple[UUID, str]] = field(default_factory=list)
    failures: list[tuple[UUID, str, PublishFailureCode, timedelta]] = field(default_factory=list)
    closed: bool = False

    def lease_pending(
        self,
        *,
        lease_owner: str,
        lease_duration: timedelta,
        batch_size: int,
    ) -> list[OutboxLease]:
        if self.lease_error is not None:
            raise self.lease_error
        self.leased_requests.append((lease_owner, lease_duration, batch_size))
        selected = self.leases[:batch_size]
        self.leases = self.leases[batch_size:]
        return selected

    def mark_published(
        self,
        *,
        event_id: UUID,
        lease_owner: str,
    ) -> PublishFinalizeResult:
        self.finalized.append((event_id, lease_owner))
        if self.finalize_error is not None:
            raise self.finalize_error
        return self.finalize_result

    def record_failure(
        self,
        *,
        event_id: UUID,
        lease_owner: str,
        code: PublishFailureCode,
        retry_delay: timedelta,
    ) -> bool:
        if self.failure_error is not None:
            raise self.failure_error
        self.failures.append((event_id, lease_owner, code, retry_delay))
        return True

    def is_ready(self) -> bool:
        return self.ready

    def close(self) -> None:
        self.closed = True


@dataclass
class FakePublisher:
    error: Exception | None = None
    ready: bool = True
    published: list[OutboxLease] = field(default_factory=list)

    def publish(self, lease: OutboxLease) -> None:
        self.published.append(lease)
        if self.error is not None:
            raise self.error

    def is_ready(self) -> bool:
        return self.ready


def dispatcher(
    repository: FakeOutboxRepository,
    publisher: FakePublisher,
    *,
    wait: object | None = None,
) -> OutboxDispatcher:
    return OutboxDispatcher(
        repository=repository,
        publisher=publisher,
        lease_owner="dispatcher-a",
        policy=DispatcherPolicy(
            batch_size=8,
            lease_duration=timedelta(seconds=30),
            poll_seconds=0.25,
            retry_base_seconds=1,
            retry_max_seconds=30,
        ),
        wait=wait if callable(wait) else None,
    )


def test_idle_and_confirmed_dispatch() -> None:
    repository = FakeOutboxRepository()
    publisher = FakePublisher()
    subject = dispatcher(repository, publisher)

    assert subject.dispatch_once() is DispatchCycleResult.IDLE

    lease = leased_event()
    repository.leases.append(lease)
    assert subject.dispatch_once() is DispatchCycleResult.DISPATCHED
    assert publisher.published == [lease]
    assert repository.finalized == [(EVENT_ID, "dispatcher-a")]
    assert not repository.failures
    assert repository.leased_requests[0] == (
        "dispatcher-a",
        timedelta(seconds=30),
        8,
    )


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (
            OutboxPublishError(code=PublishFailureCode.UNROUTABLE),
            PublishFailureCode.UNROUTABLE,
        ),
        (RuntimeError("private broker detail"), PublishFailureCode.PUBLISH_UNKNOWN),
    ],
)
def test_publish_failure_schedules_sanitized_retry(
    error: Exception,
    expected_code: PublishFailureCode,
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository = FakeOutboxRepository(leases=[leased_event(attempt_count=3)])
    publisher = FakePublisher(error=error)
    subject = dispatcher(repository, publisher)

    with caplog.at_level(logging.WARNING):
        assert subject.dispatch_once() is DispatchCycleResult.RETRY_SCHEDULED

    assert repository.failures == [(EVENT_ID, "dispatcher-a", expected_code, timedelta(seconds=4))]
    assert "private broker detail" not in caplog.text
    assert expected_code.value in caplog.text


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (OutboxInvariantError("bad state"), PublishFailureCode.INVARIANT_VIOLATION),
        (RuntimeError("commit response lost"), PublishFailureCode.FINALIZE_FAILED),
    ],
)
def test_post_confirm_failure_allows_at_least_once_retry(
    error: Exception,
    expected_code: PublishFailureCode,
) -> None:
    repository = FakeOutboxRepository(leases=[leased_event()], finalize_error=error)
    publisher = FakePublisher()

    assert dispatcher(repository, publisher).dispatch_once() is DispatchCycleResult.RETRY_SCHEDULED
    assert publisher.published[0].event_id == EVENT_ID
    assert repository.failures[0][2] is expected_code


def test_lease_loss_after_confirm_is_not_overwritten() -> None:
    repository = FakeOutboxRepository(
        leases=[leased_event()],
        finalize_result=PublishFinalizeResult.LEASE_LOST,
    )
    publisher = FakePublisher()

    assert dispatcher(repository, publisher).dispatch_once() is DispatchCycleResult.RETRY_SCHEDULED
    assert not repository.failures


def test_retry_backoff_is_bounded_for_large_attempt_counts() -> None:
    subject = dispatcher(FakeOutboxRepository(), FakePublisher())

    assert subject.retry_delay(1) == timedelta(seconds=1)
    assert subject.retry_delay(5) == timedelta(seconds=16)
    assert subject.retry_delay(1_000_000) == timedelta(seconds=30)


def test_readiness_close_and_run_loop_recover_from_cycle_error() -> None:
    repository = FakeOutboxRepository(lease_error=RuntimeError("database unavailable"))
    publisher = FakePublisher()
    stop = Event()

    def stop_after_wait(_seconds: float) -> bool:
        stop.set()
        return True

    subject = dispatcher(repository, publisher, wait=stop_after_wait)
    assert subject.is_ready()
    publisher.ready = False
    assert not subject.is_ready()

    subject.run_forever(stop)
    subject.close()
    assert repository.closed


def test_retry_recording_failure_is_sanitized() -> None:
    repository = FakeOutboxRepository(
        leases=[leased_event()],
        failure_error=RuntimeError("database password"),
    )
    publisher = FakePublisher(error=RuntimeError("broker password"))

    assert dispatcher(repository, publisher).dispatch_once() is DispatchCycleResult.RETRY_SCHEDULED
