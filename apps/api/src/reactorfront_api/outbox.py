from __future__ import annotations

import json
import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from threading import Event

from reactorfront_api.domain import (
    OutboxInvariantError,
    OutboxLease,
    OutboxPublisher,
    OutboxPublishError,
    OutboxRepository,
    PublishFailureCode,
    PublishFinalizeResult,
)

LOGGER = logging.getLogger(__name__)


class DispatchCycleResult(StrEnum):
    IDLE = "idle"
    DISPATCHED = "dispatched"
    RETRY_SCHEDULED = "retry_scheduled"


@dataclass(frozen=True, slots=True)
class DispatcherPolicy:
    batch_size: int
    lease_duration: timedelta
    poll_seconds: float
    retry_base_seconds: float
    retry_max_seconds: float


class OutboxDispatcher:
    def __init__(
        self,
        *,
        repository: OutboxRepository,
        publisher: OutboxPublisher,
        lease_owner: str,
        policy: DispatcherPolicy,
        wait: Callable[[float], bool] | None = None,
    ) -> None:
        self._repository = repository
        self._publisher = publisher
        self._lease_owner = lease_owner
        self._policy = policy
        self._wait = wait

    def dispatch_once(self) -> DispatchCycleResult:
        leases = self._repository.lease_pending(
            lease_owner=self._lease_owner,
            lease_duration=self._policy.lease_duration,
            batch_size=self._policy.batch_size,
        )
        if not leases:
            return DispatchCycleResult.IDLE

        retry_scheduled = False
        for lease in leases:
            if not self._dispatch_lease(lease):
                retry_scheduled = True
        if retry_scheduled:
            return DispatchCycleResult.RETRY_SCHEDULED
        return DispatchCycleResult.DISPATCHED

    def run_forever(self, stop_event: Event) -> None:
        wait = self._wait or stop_event.wait
        self._log("dispatcher_started", lease_owner=self._lease_owner)
        while not stop_event.is_set():
            try:
                result = self.dispatch_once()
            except Exception:
                self._log(
                    "dispatcher_cycle_failed",
                    level=logging.ERROR,
                    lease_owner=self._lease_owner,
                    failure_code=PublishFailureCode.PUBLISH_UNKNOWN.value,
                )
                result = DispatchCycleResult.RETRY_SCHEDULED
            if result is not DispatchCycleResult.DISPATCHED:
                wait(self._policy.poll_seconds)
        self._log("dispatcher_stopped", lease_owner=self._lease_owner)

    def is_ready(self) -> bool:
        return self._repository.is_ready() and self._publisher.is_ready()

    def close(self) -> None:
        self._repository.close()

    def _dispatch_lease(self, lease: OutboxLease) -> bool:
        try:
            self._publisher.publish(lease)
        except OutboxPublishError as error:
            self._schedule_retry(lease=lease, code=error.code)
            return False
        except Exception:
            self._schedule_retry(lease=lease, code=PublishFailureCode.PUBLISH_UNKNOWN)
            return False

        try:
            result = self._repository.mark_published(
                event_id=lease.event_id,
                lease_owner=lease.lease_owner,
                attempt_count=lease.attempt_count,
            )
        except OutboxInvariantError:
            self._schedule_retry(lease=lease, code=PublishFailureCode.INVARIANT_VIOLATION)
            return False
        except Exception:
            self._schedule_retry(lease=lease, code=PublishFailureCode.FINALIZE_FAILED)
            return False

        if result is PublishFinalizeResult.LEASE_LOST:
            self._log_lease(
                "outbox_lease_lost_after_confirm",
                lease,
                level=logging.WARNING,
            )
            return False
        self._log_lease(
            "outbox_published",
            lease,
            finalize_result=result.value,
        )
        return True

    def _schedule_retry(self, *, lease: OutboxLease, code: PublishFailureCode) -> None:
        delay = self.retry_delay(lease.attempt_count)
        recorded = False
        try:
            recorded = self._repository.record_failure(
                event_id=lease.event_id,
                lease_owner=lease.lease_owner,
                attempt_count=lease.attempt_count,
                code=code,
                retry_delay=delay,
            )
        except Exception:
            code = PublishFailureCode.FINALIZE_FAILED
        self._log_lease(
            "outbox_publish_retry",
            lease,
            level=logging.WARNING,
            failure_code=code.value,
            retry_recorded=recorded,
            retry_seconds=delay.total_seconds(),
        )

    def retry_delay(self, attempt_count: int) -> timedelta:
        exponent = max(attempt_count - 1, 0)
        maximum_exponent = max(
            0,
            math.ceil(math.log2(self._policy.retry_max_seconds / self._policy.retry_base_seconds)),
        )
        seconds = min(
            self._policy.retry_base_seconds * (2 ** min(exponent, maximum_exponent)),
            self._policy.retry_max_seconds,
        )
        return timedelta(seconds=seconds)

    @classmethod
    def _log_lease(
        cls,
        event: str,
        lease: OutboxLease,
        *,
        level: int = logging.INFO,
        **fields: object,
    ) -> None:
        cls._log(
            event,
            level=level,
            event_id=str(lease.event_id),
            event_type=lease.event_type,
            job_id=str(lease.job_id),
            correlation_id=str(lease.payload.get("correlationId", "unknown")),
            lease_owner=lease.lease_owner,
            attempt_count=lease.attempt_count,
            **fields,
        )

    @staticmethod
    def _log(event: str, *, level: int = logging.INFO, **fields: object) -> None:
        LOGGER.log(
            level,
            json.dumps({"event": event, **fields}, separators=(",", ":"), sort_keys=True),
        )
