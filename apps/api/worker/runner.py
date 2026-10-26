"""Resilient job execution: distributed lock, retries with backoff and a `job_runs` log (9.7)."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from typing import Any, Protocol

from domain.shared.entities import JobRunEntity
from domain.shared.enums import JobRunStatus
from domain.shared.unit_of_work import AbstractUnitOfWork

logger = logging.getLogger("fincontrol_worker.runner")

UoWFactory = Callable[[], AbstractUnitOfWork]


class JobLock(Protocol):
    def acquire(self, name: str, ttl_seconds: int) -> str | None:
        """Return a token when the lock was taken, None when another run holds it."""

    def release(self, name: str, token: str) -> None: ...


class LocalJobLock:
    """In-process lock used when no Redis is configured (single worker)."""

    def __init__(self) -> None:
        self._held: dict[str, str] = {}
        self._guard = threading.Lock()

    def acquire(self, name: str, ttl_seconds: int) -> str | None:
        with self._guard:
            if name in self._held:
                return None
            token = uuid.uuid4().hex
            self._held[name] = token
            return token

    def release(self, name: str, token: str) -> None:
        with self._guard:
            if self._held.get(name) == token:
                del self._held[name]


_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


class RedisJobLock:
    """`SET NX EX` lock shared by every worker replica; released only by its owner."""

    def __init__(self, client: Any) -> None:
        self._client = client

    @classmethod
    def from_url(cls, redis_url: str) -> RedisJobLock:
        import redis

        return cls(redis.Redis.from_url(redis_url, decode_responses=True, socket_timeout=2.0))

    def acquire(self, name: str, ttl_seconds: int) -> str | None:
        token = uuid.uuid4().hex
        return (
            token if self._client.set(f"lock:job:{name}", token, nx=True, ex=ttl_seconds) else None
        )

    def release(self, name: str, token: str) -> None:
        self._client.eval(_RELEASE_SCRIPT, 1, f"lock:job:{name}", token)


def build_job_lock(redis_url: str | None) -> JobLock:
    if redis_url and redis_url.strip():
        return RedisJobLock.from_url(redis_url.strip())
    return LocalJobLock()


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 3
    backoff_seconds: float = 30.0
    lock_ttl_seconds: int = 3600


def _details(result: Any) -> dict[str, Any]:
    if result is None:
        return {}
    if isinstance(result, dict):
        return {str(k): v for k, v in result.items()}
    if isinstance(result, int | float):
        return {"count": result}
    snapshot_date = getattr(result, "snapshot_date", None)
    if isinstance(snapshot_date, date):
        return {"snapshot_date": snapshot_date.isoformat()}
    return {"result": str(result)}


def _record(uow_factory: UoWFactory, run: JobRunEntity) -> JobRunEntity:
    with uow_factory() as uow:
        saved = uow.job_runs.update(run) if run.id else uow.job_runs.add(run)
        uow.commit()
        return saved


def run_job(
    name: str,
    job: Callable[[], Any],
    *,
    uow_factory: UoWFactory,
    lock: JobLock,
    policy: RetryPolicy,
    sleep: Callable[[float], None] = time.sleep,
) -> JobRunEntity:
    """Run `job` once under a lock, retrying with exponential backoff, and log it in job_runs.

    Never raises: failures are logged and recorded so the scheduler keeps running.
    """
    now = datetime.now(UTC)
    token = lock.acquire(name, policy.lock_ttl_seconds)
    if token is None:
        logger.info("Job %s skipped: another run holds the lock", name, extra={"job": name})
        return _record(
            uow_factory,
            JobRunEntity(
                job_name=name, started_at=now, status=JobRunStatus.SKIPPED, finished_at=now
            ),
        )

    run = _record(uow_factory, JobRunEntity(job_name=name, started_at=now))
    try:
        for attempt in range(1, policy.max_retries + 2):
            try:
                result = job()
            except Exception as exc:
                logger.warning(
                    "Job %s attempt %d failed: %s",
                    name,
                    attempt,
                    exc,
                    extra={"job": name, "attempt": attempt},
                )
                if attempt > policy.max_retries:
                    logger.exception("Job %s failed after %d attempts", name, attempt)
                    return _record(
                        uow_factory,
                        replace(
                            run,
                            status=JobRunStatus.FAILED,
                            attempts=attempt,
                            finished_at=datetime.now(UTC),
                            error=f"{type(exc).__name__}: {exc}",
                        ),
                    )
                sleep(policy.backoff_seconds * 2 ** (attempt - 1))
                continue
            logger.info("Job %s succeeded", name, extra={"job": name, "attempt": attempt})
            return _record(
                uow_factory,
                replace(
                    run,
                    status=JobRunStatus.SUCCESS,
                    attempts=attempt,
                    finished_at=datetime.now(UTC),
                    details=_details(result),
                ),
            )
        raise AssertionError("unreachable")
    finally:
        lock.release(name, token)
