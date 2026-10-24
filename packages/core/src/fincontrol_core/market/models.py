"""Normalized market data models (Quotes, PricePoints, Fundamentals) independent of provider."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime
from enum import StrEnum
from typing import Any


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
    """Normalized fundamental indicators. Percentages are expressed as fractions (0.12 = 12%)."""

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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Fundamentals:
        valid_fields = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in valid_fields})


def as_fraction(value: float | None) -> float | None:
    """Normalize percentage values that some providers return on a 0-100 scale."""
    if value is None:
        return None
    return value / 100.0 if abs(value) > 1.5 else value
