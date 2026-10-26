"""Pydantic request/response DTOs for the research module.

Scope: B3 catalog screener and watchlist.
"""

from __future__ import annotations

from datetime import datetime

from fincontrol_core.domain.enums import (
    ArcaClass,
    AssetLifecycle,
    AssetType,
    ChecklistProfile,
)
from pydantic import BaseModel, Field


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
