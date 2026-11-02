"""The concrete market gateway implements the domain port (Phase 48.R1)."""

from __future__ import annotations

import inspect

from domain.shared.gateways import CacheProbe, MarketDataGateway
from infra.cache.redis_cache import InMemoryCache, RedisCache
from infra.providers.gateway import CachedMarketGateway


def _members(protocol: type) -> set[str]:
    return {
        name
        for name in vars(protocol)
        if not name.startswith("_") and callable(getattr(protocol, name))
    }


def test_cached_gateway_has_every_method_of_the_port() -> None:
    for name in _members(MarketDataGateway):
        port = inspect.signature(getattr(MarketDataGateway, name))
        concrete = inspect.signature(getattr(CachedMarketGateway, name))
        assert list(port.parameters) == list(concrete.parameters), name


def test_cache_backends_answer_the_readiness_probe() -> None:
    assert _members(CacheProbe) == {"ping"}
    for backend in (InMemoryCache, RedisCache):
        assert callable(backend.ping)
        assert isinstance(backend.backend_name, str)


def test_the_gateway_exposes_its_cache() -> None:
    gateway = CachedMarketGateway(cache=InMemoryCache())
    assert gateway.cache.ping() is True
    assert gateway.cache.backend_name == "memory"
