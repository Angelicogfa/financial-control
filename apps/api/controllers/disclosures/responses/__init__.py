"""Pydantic response DTOs of the CVM disclosures (Phase 28)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class CvmDocumentDTO(BaseModel):
    """One IPE document of a followed company."""

    id: int
    protocol: str
    tickers: list[str] = Field(default_factory=list)
    company_name: str
    category: str
    doc_type: str = ""
    species: str = ""
    subject: str = ""
    reference_date: date | None = None
    delivery_date: date
    version: int = 1
    link: str = ""
    read: bool = False
    first_seen_at: datetime | None = None


class DisclosureFeedDTO(BaseModel):
    items: list[CvmDocumentDTO] = Field(default_factory=list)
    unread_count: int = 0
    category_counts: dict[str, int] = Field(default_factory=dict)
    # Companies in scope and the tickers without a CNPJ in the FCA map yet.
    companies: int = 0
    unmapped: list[str] = Field(default_factory=list)
    latest_delivery: date | None = None
    note: str | None = None


class MarkReadResultDTO(BaseModel):
    updated: int


class StatementDeliveryDTO(BaseModel):
    """What was known right after a statement was delivered: 12-month flows, last balance."""

    reference_date: date
    delivered_on: date
    doc_type: Literal["DFP", "ITR"]
    version: int
    revenue: float | None = None
    ebit: float | None = None
    ebitda: float | None = None
    net_income: float | None = None
    dividends_paid: float | None = None
    equity: float | None = None
    net_debt: float | None = None
    total_assets: float | None = None
    shares_outstanding: float | None = None


class StatementValuationDTO(BaseModel):
    """Indicators from the last delivered statement and the stored quote."""

    price: float
    price_date: date | None = None
    market_cap: float
    earnings_yield: float | None = None
    dividend_yield: float | None = None
    price_to_book: float | None = None
    ev_to_ebitda: float | None = None


class AssetStatementsDTO(BaseModel):
    """Statements delivered to the CVM by the asset's company, point in time (Phase 42.2)."""

    asset_id: int
    ticker: str
    status: Literal["OK", "NOT_A_COMPANY", "NOT_MAPPED", "NOT_LOADED"]
    cnpj: str | None = None
    template: Literal["COMPANY", "FINANCIAL"] | None = None
    deliveries: list[StatementDeliveryDTO] = Field(default_factory=list)
    valuation: StatementValuationDTO | None = None
    years_loaded: list[int] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
