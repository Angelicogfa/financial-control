"""Job locks: one run of each job at a time, across every worker replica.

Redis `SET NX EX` when a Redis URL is configured, an in-process lock otherwise.
"""

from __future__ import annotations

import threading
import uuid
from typing import Any, Protocol


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


__all__ = ["JobLock", "LocalJobLock", "RedisJobLock", "build_job_lock"]
