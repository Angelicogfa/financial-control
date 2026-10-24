"""Cache backends (Redis and thread-safe in-memory TTL fallback) for market data."""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from typing import Any


class AbstractCacheBackend(ABC):
    """Port for key-value JSON caching with TTL."""

    @abstractmethod
    def get_json(self, key: str) -> dict[str, Any] | list[Any] | None:
        """Retrieve a cached JSON-serializable payload or None if expired/missing."""

    @abstractmethod
    def set_json(self, key: str, value: dict[str, Any] | list[Any], ttl_seconds: int) -> None:
        """Store a JSON-serializable payload with a time-to-live in seconds."""


class InMemoryCache(AbstractCacheBackend):
    """Lightweight in-memory TTL cache for local execution, unit tests, and Redis fallback."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, str]] = {}

    def get_json(self, key: str) -> dict[str, Any] | list[Any] | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, raw = entry
        if time.monotonic() > expires_at:
            self._store.pop(key, None)
            return None
        return json.loads(raw)

    def set_json(self, key: str, value: dict[str, Any] | list[Any], ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        expires_at = time.monotonic() + ttl_seconds
        self._store[key] = (expires_at, json.dumps(value))

    def clear(self) -> None:
        self._store.clear()


class RedisCache(AbstractCacheBackend):
    """Redis-backed cache with transparent fallback to InMemoryCache on connection errors."""

    def __init__(self, redis_url: str, fallback: InMemoryCache | None = None) -> None:
        import redis

        self._client = redis.Redis.from_url(redis_url, decode_responses=True, socket_timeout=1.5)
        self._fallback = fallback or InMemoryCache()

    def get_json(self, key: str) -> dict[str, Any] | list[Any] | None:
        try:
            raw = self._client.get(key)
            if raw is not None:
                return json.loads(str(raw))
        except Exception:
            return self._fallback.get_json(key)
        return None

    def set_json(self, key: str, value: dict[str, Any] | list[Any], ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        payload = json.dumps(value)
        try:
            self._client.setex(key, ttl_seconds, payload)
        except Exception:
            self._fallback.set_json(key, value, ttl_seconds)


def build_cache_backend(redis_url: str | None = None) -> AbstractCacheBackend:
    """Create a RedisCache when `redis_url` is provided, otherwise an InMemoryCache."""
    if redis_url and redis_url.strip():
        try:
            return RedisCache(redis_url.strip())
        except Exception:
            return InMemoryCache()
    return InMemoryCache()
