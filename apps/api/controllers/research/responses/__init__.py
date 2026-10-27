"""Pydantic request/response DTOs for the research module.

Scope: B3 catalog screener and watchlist.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from domain.shared.enums import (
    ArcaClass,
    AssetLifecycle,
    AssetType,
    ChecklistProfile,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    FixedIncomeLiquidity,
)


class ScreenerItemDTO(BaseModel):
    ticker: str
    name: str
    asset_type: AssetType
    arca_class: ArcaClass
    sector: str | None = None
    close: float | None = None
    change_pct: float | None = None
    volume_brl: float | None = None
    market_cap: float | None = None
    logo_url: str | None = None
    price_to_earnings: float | None = None
    price_to_book: float | None = None
    dividend_yield: float | None = None
    return_on_equity: float | None = None
    valuation_verdict: str | None = None
    fair_value: float | None = None
    margin: float | None = None
    asset_id: int | None = None
    lifecycle_status: AssetLifecycle | None = None


class ScreenerResponseDTO(BaseModel):
    results: list[ScreenerItemDTO]
    candidates: int
    scanned: int
    truncated: bool
    arca_classes: list[ArcaClass] = Field(default_factory=list)
    catalog_size: int
    catalog_updated_at: datetime | None = None


class WatchlistAddRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=32)
    asset_type: AssetType | None = None
    name: str | None = Field(default=None, max_length=160)
    arca_class: ArcaClass | None = Field(
        default=None, description="ARCA quadrant chosen by the user; omitted = the suggested one"
    )


class WatchlistClassifyRequest(BaseModel):
    arca_class: ArcaClass


class WatchlistItemDTO(BaseModel):
    asset_id: int
    ticker: str
    name: str
    asset_type: AssetType
    arca_class: ArcaClass
    lifecycle_status: AssetLifecycle
    eligible: bool
    price: float | None = None
    change_pct: float | None = None
    checklist_profile: ChecklistProfile
    checklist_score: int
    checklist_normalized_score: float | None = None
    checklist_coverage_pct: float
    checklist_recommendation: str
    valuation_verdict: str
    fair_value: float | None = None
    margin: float | None = None


class TreasuryBondDTO(BaseModel):
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
    contracted_rate_percent: float
    liquidity: FixedIncomeLiquidity
    asset_id: int | None = None


class TreasurySearchResponseDTO(BaseModel):
    results: list[TreasuryBondDTO]
    total: int
    unavailable_reason: str | None = None
