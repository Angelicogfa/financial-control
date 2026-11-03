"""Response schemas of the instrument page and of the global search (Phase 48.R2)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from domain.instruments.read_models import InstrumentKind, MatchKind, QuoteSource


class InstrumentQuoteDTO(BaseModel):
    price: float
    currency: str
    source: QuoteSource
    change_pct: float | None = Field(default=None, description="Change of the day as a fraction")
    as_of: datetime | None = None
    freshness: str | None = None


class InstrumentIndicatorsDTO(BaseModel):
    fetched_at: datetime | None = None
    price_to_earnings: float | None = None
    price_to_book: float | None = None
    dividend_yield: float | None = None
    return_on_equity: float | None = None
    profit_margin: float | None = None
    net_debt_to_ebitda: float | None = None
    market_cap: float | None = None
    avg_daily_volume: float | None = None
    suspicious: bool = False


class InstrumentLensDTO(BaseModel):
    lens: str
    normalized: float | None = None
    confidence: float
    note: str


class InstrumentLensesDTO(BaseModel):
    as_of: date
    source: str
    arca_class: str | None = None
    sector: str
    eligible: bool | None = None
    items: list[InstrumentLensDTO]


class ForecastBandDTO(BaseModel):
    months: int
    p5: float
    p50: float
    p95: float
    up_probability: float


class InstrumentForecastDTO(BaseModel):
    status: str = Field(description="OK | NOT_COMPUTED | INSUFFICIENT_HISTORY | LOW_CONFIDENCE")
    seal_level: int
    seal_label: str
    as_of: date | None = None
    price_now: float | None = None
    bands: list[ForecastBandDTO] = Field(default_factory=list)


class InstrumentTrackingDTO(BaseModel):
    asset_id: int
    is_active: bool
    holds_position: bool
    arca_class: str | None = None
    purpose: str


class TreasuryTermsDTO(BaseModel):
    bond_type: str
    maturity_date: date
    indexer: str
    liquidity: str
    buy_rate: float | None = None
    sell_rate: float | None = None
    buy_price: float | None = None
    sell_price: float | None = None
    base_date: date | None = None


class InstrumentViewDTO(BaseModel):
    """Any ticker or Tesouro bond, registered or not; only what the database already has."""

    key: str
    kind: InstrumentKind
    ticker: str
    name: str
    asset_type: str | None = None
    sector: str | None = None
    logo_url: str | None = None
    in_catalog: bool
    quote: InstrumentQuoteDTO | None = None
    indicators: InstrumentIndicatorsDTO | None = None
    lenses: InstrumentLensesDTO | None = None
    forecast: InstrumentForecastDTO | None = None
    tracking: InstrumentTrackingDTO | None = Field(
        default=None,
        description="The registered asset; its id opens checklist, tax and ledger in /assets/{id}",
    )
    treasury: TreasuryTermsDTO | None = None
    data_gaps: list[str] = Field(default_factory=list)


class SearchHitDTO(BaseModel):
    key: str
    kind: InstrumentKind
    ticker: str
    name: str
    asset_type: str | None = None
    sector: str | None = None
    close: float | None = None
    match: MatchKind
    tracked_asset_id: int | None = None
    holds_position: bool = False


class SearchResultDTO(BaseModel):
    query: str
    hits: list[SearchHitDTO]
    total: int
