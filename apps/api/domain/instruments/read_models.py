"""Read models of the instrument page and of the global search (Phase 48.R2).

An instrument is anything the market lists, by ticker (B3 catalog, stored quotes, registered
assets) or by Tesouro Direto symbol (`tesouro-ipca-15052035`). Opening one never registers
it: `assets` stays "what I follow or own".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

from core.errors import ValidationError

TREASURY_PREFIX = "tesouro-"
# Registered fixed income, Tesouro and cash assets carry generated codes such as
# `TESOURO_IPCA-TESOURONAC-2032` (domain/assets/services/codes.py), hence the underscore.
_TICKER = re.compile(r"^[A-Z0-9][A-Z0-9_.\-=^]{0,31}$")
_TREASURY = re.compile(r"^tesouro-[a-z0-9\-]{1,60}$")


class InstrumentKind(StrEnum):
    LISTED = "LISTED"  # a ticker: B3 catalog, stored quote or registered asset
    TREASURY = "TREASURY"  # a Tesouro Direto bond of the catalog


class QuoteSource(StrEnum):
    STORED_QUOTE = "STORED_QUOTE"  # last quote the worker saved
    CATALOG_CLOSE = "CATALOG_CLOSE"  # close of the last session in the B3 catalog
    TREASURY_PRICE = "TREASURY_PRICE"  # unit price published by the Tesouro
    MANUAL = "MANUAL"  # manual price of a registered asset


@dataclass(frozen=True)
class InstrumentKey:
    value: str
    kind: InstrumentKind


def instrument_key(raw: str) -> InstrumentKey:
    """Normalize a ticker (upper case) or a Tesouro symbol (lower case slug)."""
    text = (raw or "").strip()
    if text.lower().startswith(TREASURY_PREFIX):
        slug = text.lower()
        if not _TREASURY.match(slug):
            raise ValidationError(f"invalid Tesouro symbol: {raw!r}", code="INVALID_INSTRUMENT")
        return InstrumentKey(slug, InstrumentKind.TREASURY)
    ticker = text.upper()
    if not _TICKER.match(ticker):
        raise ValidationError(f"invalid ticker: {raw!r}", code="INVALID_INSTRUMENT")
    return InstrumentKey(ticker, InstrumentKind.LISTED)


@dataclass(frozen=True)
class InstrumentQuote:
    price: float
    currency: str
    source: QuoteSource
    change_pct: float | None = None  # fraction of the day (0.012 = +1.2%)
    as_of: datetime | None = None
    freshness: str | None = None  # QuoteFreshness of a stored quote


@dataclass(frozen=True)
class InstrumentIndicators:
    """Current indicators stored for the ticker (`market_data.fundamentals`)."""

    fetched_at: datetime | None
    price_to_earnings: float | None = None
    price_to_book: float | None = None
    dividend_yield: float | None = None
    return_on_equity: float | None = None
    profit_margin: float | None = None
    net_debt_to_ebitda: float | None = None
    market_cap: float | None = None
    avg_daily_volume: float | None = None
    suspicious: bool = False


@dataclass(frozen=True)
class InstrumentLens:
    lens: str
    normalized: float | None  # [0, 1], higher is better
    confidence: float
    note: str


@dataclass(frozen=True)
class InstrumentLenses:
    as_of: date
    source: str
    arca_class: str | None
    sector: str
    eligible: bool | None  # None: the gates were not computed for it
    items: list[InstrumentLens]


@dataclass(frozen=True)
class ForecastBand:
    months: int
    p5: float
    p50: float
    p95: float
    up_probability: float


@dataclass(frozen=True)
class InstrumentForecast:
    status: str  # OK | NOT_COMPUTED | INSUFFICIENT_HISTORY | LOW_CONFIDENCE
    seal_level: int
    seal_label: str
    as_of: date | None = None
    price_now: float | None = None
    bands: list[ForecastBand] = field(default_factory=list)


@dataclass(frozen=True)
class InstrumentTracking:
    """The registered asset with this ticker: watched, owned or archived."""

    asset_id: int
    is_active: bool
    holds_position: bool
    arca_class: str | None
    purpose: str


@dataclass(frozen=True)
class TreasuryTerms:
    bond_type: str
    maturity_date: date
    indexer: str
    liquidity: str
    buy_rate: float | None
    sell_rate: float | None
    buy_price: float | None
    sell_price: float | None
    base_date: date | None


@dataclass(frozen=True)
class InstrumentView:
    key: str
    kind: InstrumentKind
    ticker: str
    name: str
    asset_type: str | None
    sector: str | None
    logo_url: str | None
    in_catalog: bool
    quote: InstrumentQuote | None
    indicators: InstrumentIndicators | None
    lenses: InstrumentLenses | None
    forecast: InstrumentForecast | None
    tracking: InstrumentTracking | None
    treasury: TreasuryTerms | None
    # What is still missing in the database, in plain words, so the page can say it.
    data_gaps: list[str] = field(default_factory=list)


class MatchKind(StrEnum):
    TICKER_EXACT = "TICKER_EXACT"
    TICKER_PREFIX = "TICKER_PREFIX"
    NAME_PREFIX = "NAME_PREFIX"
    NAME_CONTAINS = "NAME_CONTAINS"


@dataclass(frozen=True)
class SearchHit:
    key: str
    kind: InstrumentKind
    ticker: str
    name: str
    asset_type: str | None
    sector: str | None
    close: float | None
    match: MatchKind
    tracked_asset_id: int | None = None
    holds_position: bool = False


@dataclass(frozen=True)
class SearchResult:
    query: str
    hits: list[SearchHit]
    total: int  # matches before the limit
