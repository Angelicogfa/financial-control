"""Market data port: what the domain asks of the market gateway (Phase 48.R1).

`infra.providers.gateway.CachedMarketGateway` implements it; the composition root injects
it. The domain depends only on this protocol, never on the providers or the cache.
"""

from __future__ import annotations

from typing import Protocol

from domain.assets.services.history import FundamentalSnapshot
from domain.market.entities import (
    AnnouncedDistributions,
    Fundamentals,
    PricePoint,
    Quote,
    TreasuryCatalogResult,
)
from domain.shared.enums import AssetType, Market


class CacheProbe(Protocol):
    backend_name: str

    def ping(self) -> bool: ...


class MarketDataGateway(Protocol):
    cache: CacheProbe

    def get_quote(
        self,
        symbol: str,
        *,
        asset_type: AssetType | None = None,
        market: Market | None = None,
        bypass_cache: bool = False,
    ) -> Quote | None: ...

    def get_history(
        self,
        symbol: str,
        *,
        range_period: str = "1y",
        asset_type: AssetType | None = None,
        market: Market | None = None,
        bypass_cache: bool = False,
    ) -> list[PricePoint]: ...

    def get_fundamentals(
        self,
        symbol: str,
        *,
        asset_type: AssetType | None = None,
        market: Market | None = None,
        bypass_cache: bool = False,
    ) -> Fundamentals | None: ...

    def get_distributions(
        self,
        symbol: str,
        *,
        asset_type: AssetType | None = None,
        bypass_cache: bool = False,
    ) -> AnnouncedDistributions: ...

    def get_annual_statements(
        self,
        symbol: str,
        *,
        asset_type: AssetType | None = None,
        bypass_cache: bool = False,
    ) -> list[FundamentalSnapshot]: ...

    def list_treasury_bonds(self, *, bypass_cache: bool = False) -> TreasuryCatalogResult: ...

    def get_usd_brl_rate(self) -> float: ...

    def get_macro_rates(self) -> tuple[float, float]: ...

    def report_fetch_timeout(self, kind: str, ticker: str, timeout_seconds: float) -> None:
        """Record a batch fetch that missed its deadline (a worker request error)."""
        ...
