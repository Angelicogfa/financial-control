"""Normalized market data models (Quotes, PricePoints, Fundamentals) independent of provider."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from domain.shared.enums import (
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    FixedIncomeLiquidity,
)


class QuoteFreshness(StrEnum):
    """Indicates how the quote or curve price was obtained."""

    LIVE = "LIVE"
    CACHED = "CACHED"
    FALLBACK = "FALLBACK"
    CURVE = "CURVE"
    MANUAL = "MANUAL"


@dataclass(frozen=True)
class Quote:
    """Normalized market quote for a symbol."""

    symbol: str
    price: float
    currency: str = "BRL"
    name: str | None = None
    change_pct: float | None = None
    previous_close: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    volume: float | None = None
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    market_cap: float | None = None
    logo_url: str | None = None
    market_time: datetime | None = None
    provider: str | None = None
    freshness: QuoteFreshness = QuoteFreshness.LIVE

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["market_time"] = self.market_time.isoformat() if self.market_time else None
        data["freshness"] = self.freshness.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Quote:
        payload = dict(data)
        if payload.get("market_time") and isinstance(payload["market_time"], str):
            payload["market_time"] = datetime.fromisoformat(payload["market_time"])
        if payload.get("freshness"):
            payload["freshness"] = QuoteFreshness(payload["freshness"])
        valid_fields = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in payload.items() if k in valid_fields})


@dataclass(frozen=True)
class PricePoint:
    """Daily OHLCV price point."""

    date: date
    close: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    adj_close: float | None = None
    volume: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["date"] = self.date.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PricePoint:
        payload = dict(data)
        if isinstance(payload.get("date"), str):
            payload["date"] = date.fromisoformat(payload["date"])
        valid_fields = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in payload.items() if k in valid_fields})


@dataclass(frozen=True)
class Fundamentals:
    """Normalized fundamental indicators (ADR 0006).

    Percentages are fractions (0.12 = 12%), multiples are plain ratios and
    `avg_daily_volume` is the average *financial* volume in the trading currency.
    """

    symbol: str
    sector: str | None = None
    industry: str | None = None
    price_to_earnings: float | None = None
    price_to_book: float | None = None
    earnings_per_share: float | None = None
    book_value_per_share: float | None = None
    dividend_yield: float | None = None
    dividends_per_share_ttm: float | None = None
    return_on_equity: float | None = None
    profit_margin: float | None = None
    debt_to_equity: float | None = None
    net_debt_to_ebitda: float | None = None
    revenue_growth: float | None = None
    earnings_growth: float | None = None
    market_cap: float | None = None
    avg_daily_volume: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    # Indicator -> reason (pt-BR) for values out of range or diverging between sources.
    suspicious: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Fundamentals:
        valid_fields = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in valid_fields})


@dataclass(frozen=True)
class StoredMarketData:
    """The last quote and fundamentals the worker saved for a ticker (Phase 38).

    Screens read these instead of calling the providers; each part carries when it was fetched.
    """

    ticker: str
    quote: Quote | None = None
    quote_fetched_at: datetime | None = None
    fundamentals: Fundamentals | None = None
    fundamentals_fetched_at: datetime | None = None
    # Phase 39: declared distributions and when the full price history was first loaded.
    distributions: AnnouncedDistributions | None = None
    distributions_fetched_at: datetime | None = None
    history_loaded_at: datetime | None = None


@dataclass(frozen=True)
class QuoteDay:
    """The last quote of a ticker on a day, kept for audit (Phase 39.1)."""

    ticker: str
    day: date
    price: float
    currency: str
    provider: str | None
    freshness: str
    fetched_at: datetime


def distributions_to_dict(value: AnnouncedDistributions) -> dict[str, Any]:
    return {"cash": [i.to_dict() for i in value.cash], "stock": [i.to_dict() for i in value.stock]}


def distributions_from_dict(data: dict[str, Any]) -> AnnouncedDistributions:
    return AnnouncedDistributions(
        cash=[AnnouncedEarning.from_dict(i) for i in data.get("cash", [])],
        stock=[AnnouncedStockEvent.from_dict(i) for i in data.get("stock", [])],
    )


def financial_volume(volume_shares: float | None, price: float | None) -> float | None:
    """Average financial volume (shares traded x price) used by liquidity rules (I-10)."""
    if volume_shares is None or price is None or price <= 0:
        return None
    return volume_shares * price


@dataclass(frozen=True)
class TreasuryBond:
    """Normalized Brazilian Treasury bond (Tesouro Direto) from upstream market provider."""

    symbol: str
    name: str
    bond_type: str
    instrument_kind: FixedIncomeInstrumentKind
    indexer: FixedIncomeIndexer
    raw_indexer: str
    coupon_type: str
    maturity_date: date
    duration_days: int | None = None
    base_date: date | None = None
    buy_rate: float | None = None
    sell_rate: float | None = None
    buy_price: float | None = None
    sell_price: float | None = None
    base_price: float | None = None
    rate_type: str | None = None
    rate_unit: str | None = None
    rate_description: str | None = None
    contracted_rate_percent: float = 100.0
    liquidity: FixedIncomeLiquidity = FixedIncomeLiquidity.DAILY
    source: str | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["instrument_kind"] = self.instrument_kind.value
        data["indexer"] = self.indexer.value
        data["liquidity"] = self.liquidity.value
        data["maturity_date"] = self.maturity_date.isoformat()
        data["base_date"] = self.base_date.isoformat() if self.base_date else None
        data["updated_at"] = self.updated_at.isoformat() if self.updated_at else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TreasuryBond:
        payload = dict(data)
        if isinstance(payload.get("instrument_kind"), str):
            payload["instrument_kind"] = FixedIncomeInstrumentKind(payload["instrument_kind"])
        if isinstance(payload.get("indexer"), str):
            payload["indexer"] = FixedIncomeIndexer(payload["indexer"])
        if isinstance(payload.get("liquidity"), str):
            payload["liquidity"] = FixedIncomeLiquidity(payload["liquidity"])
        if isinstance(payload.get("maturity_date"), str):
            payload["maturity_date"] = date.fromisoformat(payload["maturity_date"])
        if isinstance(payload.get("base_date"), str):
            payload["base_date"] = date.fromisoformat(payload["base_date"])
        if isinstance(payload.get("updated_at"), str):
            payload["updated_at"] = datetime.fromisoformat(payload["updated_at"])
        valid_fields = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in payload.items() if k in valid_fields})


@dataclass(frozen=True)
class TreasuryCatalogResult:
    """Outcome of querying the upstream Treasury catalog."""

    results: list[TreasuryBond] = field(default_factory=list)
    unavailable_reason: str | None = None


@dataclass(frozen=True)
class AnnouncedEarning:
    """A cash distribution declared by the issuer (item 26.3).

    `com_date` is the last day to hold the share with the right (data com); the ex date is the
    next business day. `rate` is the gross amount per share in the trading currency.
    """

    ticker: str
    label: str
    rate: float
    com_date: date | None
    payment_date: date | None
    approved_on: date | None = None
    related_to: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("com_date", "payment_date", "approved_on"):
            value = data[key]
            data[key] = value.isoformat() if value else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnnouncedEarning:
        payload = dict(data)
        for key in ("com_date", "payment_date", "approved_on"):
            value = payload.get(key)
            payload[key] = date.fromisoformat(value) if value else None
        return cls(**payload)


@dataclass(frozen=True)
class AnnouncedStockEvent:
    """A split, reverse split or bonus issue declared by the issuer (data com included)."""

    ticker: str
    label: str
    factor: float | None
    com_date: date | None
    approved_on: date | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("com_date", "approved_on"):
            value = data[key]
            data[key] = value.isoformat() if value else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnnouncedStockEvent:
        payload = dict(data)
        for key in ("com_date", "approved_on"):
            value = payload.get(key)
            payload[key] = date.fromisoformat(value) if value else None
        return cls(**payload)


@dataclass(frozen=True)
class AnnouncedDistributions:
    """Cash and stock distributions of a ticker as published by the provider."""

    cash: list[AnnouncedEarning] = field(default_factory=list)
    stock: list[AnnouncedStockEvent] = field(default_factory=list)
