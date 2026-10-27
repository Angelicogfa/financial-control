"""CachedMarketGateway routing requests to Brapi, YFinance, and BCB with Redis/InMemory cache."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from domain.assets.services.history import (
    FundamentalSnapshot,
    snapshot_from_dict,
    snapshot_to_dict,
)
from domain.market.entities import (
    Fundamentals,
    PricePoint,
    Quote,
    QuoteFreshness,
    TreasuryBond,
    TreasuryCatalogResult,
)
from domain.shared.entities import CatalogInstrument, MarketSeriesPoint
from domain.shared.enums import AssetType, Market, market_for
from infra.cache.redis_cache import AbstractCacheBackend, InMemoryCache
from infra.providers.bcb import BcbSgsProvider
from infra.providers.brapi import BrapiProvider
from infra.providers.yfinance_provider import YFinanceProvider


class CachedMarketGateway:
    """Unified gateway for market quotes, historical series, fundamentals, FX, and BCB rates."""

    def __init__(
        self,
        brapi: BrapiProvider | None = None,
        yfinance: YFinanceProvider | None = None,
        bcb: BcbSgsProvider | None = None,
        cache: AbstractCacheBackend | None = None,
        quote_ttl_seconds: int = 900,
        fundamentals_ttl_seconds: int = 86400,
        history_ttl_seconds: int = 21600,
        default_usd_brl: float = 5.15,
        miss_ttl_seconds: int = 300,
    ) -> None:
        self.brapi = brapi or BrapiProvider()
        self.yfinance = yfinance or YFinanceProvider()
        self.bcb = bcb or BcbSgsProvider()
        self.cache = cache or InMemoryCache()
        self.quote_ttl = quote_ttl_seconds
        self.fundamentals_ttl = fundamentals_ttl_seconds
        self.history_ttl = history_ttl_seconds
        self.miss_ttl = miss_ttl_seconds
        self.default_usd_brl = default_usd_brl

    # A provider failure is remembered for `miss_ttl` seconds: while the providers are down,
    # screens get the fallback at once instead of waiting for the timeout on every request.
    _MISS = {"miss": True}

    def _cached(self, key: str) -> object:
        """The cached value, `_MISS` for a recent failure, or None when nothing is cached."""
        cached = self.cache.get_json(key)
        return self._MISS if cached == self._MISS else cached

    def _remember_miss(self, key: str) -> None:
        if self.miss_ttl > 0:
            self.cache.set_json(key, self._MISS, self.miss_ttl)

    def _resolve_market(
        self,
        symbol: str,
        asset_type: AssetType | None = None,
        market: Market | None = None,
    ) -> Market:
        if market is not None:
            return market
        if asset_type is not None:
            return market_for(asset_type)
        sym = symbol.strip().upper()
        if sym in ("^BVSP", "IBOV", "IFIX", "IFIX.SA", "^GSPC", "SP500", "USDBRL=X"):
            return Market.INDEX
        # Heuristic: B3 tickers typically end with digits (e.g., WEGE3, PETR4, HGLG11, IVVB11)
        if sym and sym[-1].isdigit():
            return Market.B3
        return Market.US

    def get_quote(
        self,
        symbol: str,
        *,
        asset_type: AssetType | None = None,
        market: Market | None = None,
        bypass_cache: bool = False,
    ) -> Quote | None:
        """Retrieve quote from cache or upstream provider (Brapi -> YFinance fallback for B3)."""
        norm_sym = symbol.strip().upper()
        mkt = self._resolve_market(norm_sym, asset_type, market)
        if mkt in (Market.MANUAL, Market.FIXED_INCOME_CURVE):
            return None

        cache_key = f"quote:{mkt.value}:{norm_sym}"
        if not bypass_cache:
            cached = self._cached(cache_key)
            if cached is self._MISS:
                return None
            if isinstance(cached, dict):
                q = Quote.from_dict(cached)
                return replace(q, freshness=QuoteFreshness.CACHED)

        quote: Quote | None = None
        if mkt == Market.B3:
            quote = self.brapi.get_quote(norm_sym)
            if quote is None:
                fb = self.yfinance.get_quote(norm_sym, market=Market.B3)
                if fb is not None:
                    quote = replace(fb, freshness=QuoteFreshness.FALLBACK)
        else:
            quote = self.yfinance.get_quote(norm_sym, market=mkt)

        if quote is not None:
            self.cache.set_json(cache_key, quote.to_dict(), self.quote_ttl)
        else:
            self._remember_miss(cache_key)
        return quote

    def get_history(
        self,
        symbol: str,
        *,
        range_period: str = "1y",
        asset_type: AssetType | None = None,
        market: Market | None = None,
        bypass_cache: bool = False,
    ) -> list[PricePoint]:
        """Retrieve daily OHLCV history with cache and B3 fallback."""
        norm_sym = symbol.strip().upper()
        mkt = self._resolve_market(norm_sym, asset_type, market)
        if mkt in (Market.MANUAL, Market.FIXED_INCOME_CURVE):
            return []

        cache_key = f"history:{mkt.value}:{norm_sym}:{range_period}"
        if not bypass_cache:
            cached = self._cached(cache_key)
            if cached is self._MISS:
                return []
            if isinstance(cached, list):
                return [PricePoint.from_dict(item) for item in cached]

        points: list[PricePoint] = []
        if mkt == Market.B3:
            points = self.brapi.get_history(norm_sym, range_period=range_period)
            if not points:
                points = self.yfinance.get_history(
                    norm_sym, range_period=range_period, market=Market.B3
                )
        else:
            points = self.yfinance.get_history(norm_sym, range_period=range_period, market=mkt)

        if points:
            self.cache.set_json(cache_key, [p.to_dict() for p in points], self.history_ttl)
        else:
            self._remember_miss(cache_key)
        return points

    def get_fundamentals(
        self,
        symbol: str,
        *,
        asset_type: AssetType | None = None,
        market: Market | None = None,
        bypass_cache: bool = False,
    ) -> Fundamentals | None:
        """Retrieve fundamentals with 24h cache and B3 fallback."""
        norm_sym = symbol.strip().upper()
        mkt = self._resolve_market(norm_sym, asset_type, market)
        if mkt in (Market.MANUAL, Market.FIXED_INCOME_CURVE, Market.CRYPTO, Market.INDEX):
            return None

        cache_key = f"fundamentals:{mkt.value}:{norm_sym}"
        if not bypass_cache:
            cached = self._cached(cache_key)
            if cached is self._MISS:
                return None
            if isinstance(cached, dict):
                return Fundamentals.from_dict(cached)

        fund: Fundamentals | None = None
        if mkt == Market.B3:
            fund = self.brapi.get_fundamentals(norm_sym)
            if fund is None:
                fund = self.yfinance.get_fundamentals(norm_sym, market=Market.B3)
        else:
            fund = self.yfinance.get_fundamentals(norm_sym, market=mkt)

        if fund is not None:
            self.cache.set_json(cache_key, fund.to_dict(), self.fundamentals_ttl)
        else:
            self._remember_miss(cache_key)
        return fund

    def get_annual_statements(
        self,
        symbol: str,
        *,
        asset_type: AssetType | None = None,
        bypass_cache: bool = False,
    ) -> list[FundamentalSnapshot]:
        """Yearly statement history (brapi first for B3, Yahoo otherwise), cached like
        fundamentals."""
        norm_sym = symbol.strip().upper()
        mkt = self._resolve_market(norm_sym, asset_type, None)
        if mkt not in (Market.B3, Market.US):
            return []
        cache_key = f"statements:{mkt.value}:{norm_sym}"
        if not bypass_cache:
            cached = self._cached(cache_key)
            if cached is self._MISS:
                return []
            if isinstance(cached, list):
                return [snapshot_from_dict(item) for item in cached]

        snapshots: list[FundamentalSnapshot] = []
        if mkt == Market.B3:
            snapshots = self.brapi.get_annual_statements(norm_sym)
        if not snapshots:
            snapshots = self.yfinance.get_annual_statements(norm_sym, market=mkt)
        if snapshots:
            self.cache.set_json(
                cache_key, [snapshot_to_dict(s) for s in snapshots], self.fundamentals_ttl
            )
        else:
            self._remember_miss(cache_key)
        return snapshots

    def list_instruments(self) -> list[CatalogInstrument]:
        """Listed B3 instruments (not cached: the worker stores them once a day)."""
        return self.brapi.list_instruments()

    def list_treasury_bonds(
        self,
        *,
        indexer: str | None = None,
        coupon_type: str | None = None,
        search: str | None = None,
        bypass_cache: bool = False,
    ) -> TreasuryCatalogResult:
        """Fetch Brazilian Treasury bonds from Brapi (/v2/treasury/list) with short cache."""
        norm_idx = (indexer or "").strip().lower() or None
        norm_coupon = (coupon_type or "").strip().lower() or None
        norm_search = (search or "").strip() or None
        cache_key = (
            f"treasury:list:{norm_idx or 'all'}:{norm_coupon or 'all'}:"
            f"{(norm_search or '').casefold()}"
        )
        if not bypass_cache:
            cached = self._cached(cache_key)
            if isinstance(cached, dict) and isinstance(cached.get("results"), list):
                return TreasuryCatalogResult(
                    results=[TreasuryBond.from_dict(item) for item in cached["results"]],
                    unavailable_reason=cached.get("unavailable_reason"),
                )

        result = self.brapi.list_treasury_bonds(
            indexer=norm_idx,
            coupon_type=norm_coupon,
            search=norm_search,
        )
        if not result.unavailable_reason:
            self.cache.set_json(
                cache_key,
                {
                    "results": [b.to_dict() for b in result.results],
                    "unavailable_reason": None,
                },
                self.quote_ttl,
            )
        return result

    def get_usd_brl_rate(self) -> float:
        """Fetch live or cached USD/BRL exchange rate with safe fallback."""
        q = self.get_quote("USDBRL=X", market=Market.INDEX)
        if q is not None and q.price > 0:
            return q.price
        return self.default_usd_brl

    def get_macro_rates(self) -> tuple[float, float]:
        """Return (annual_cdi_rate, annual_ipca_rate) with cache."""
        cached = self.cache.get_json("macro:cdi_ipca")
        if isinstance(cached, dict) and "cdi" in cached and "ipca" in cached:
            return float(cached["cdi"]), float(cached["ipca"])

        cdi = self.bcb.get_annualized_cdi_rate()
        ipca = self.bcb.get_annualized_ipca_rate()
        self.cache.set_json("macro:cdi_ipca", {"cdi": cdi, "ipca": ipca}, self.history_ttl)
        return cdi, ipca

    def fetch_bcb_series(
        self,
        symbol: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[MarketSeriesPoint]:
        """Fetch BCB SGS series ('CDI', 'SELIC', 'IPCA')."""
        return self.bcb.fetch_series(symbol, start_date=start_date, end_date=end_date)
