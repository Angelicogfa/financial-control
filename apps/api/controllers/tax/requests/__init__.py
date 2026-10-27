"""Pydantic request DTOs for the tax module.

Scope: tax rule registry, per-asset tax status and the fixed income comparator.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from domain.tax.services.comparator import DEFAULT_PRINCIPAL, MAX_TERM_DAYS, OfferIndexer


class FixedIncomeOfferRequest(BaseModel):
    """A bond typed by hand or taken from the portfolio (`asset_id` fills missing fields).

    `rate` follows ADR 0006: CDI multiplier for CDI_PERCENT (1.10 = 110%), annual fraction for
    CDI_SPREAD, IPCA_SPREAD and PRE (0.065 = 6.5% a.a.).
    """

    label: str | None = Field(default=None, max_length=80)
    asset_id: int | None = None
    indexer: OfferIndexer | None = None
    rate: float | None = None
    term_days: int | None = Field(default=None, ge=1, le=MAX_TERM_DAYS)
    tax_exempt: bool | None = None
    grace_days: int | None = Field(default=None, ge=0, le=MAX_TERM_DAYS)


class RateScenarioRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    annual_cdi_rate: float = Field(ge=0.0, le=1.0)
    annual_ipca_rate: float = Field(ge=-0.5, le=1.0)


class FixedIncomeCompareRequest(BaseModel):
    """Offers to compare; without `scenarios` the policy's projection premises are used."""

    offers: list[FixedIncomeOfferRequest] = Field(min_length=2, max_length=10)
    principal: float = Field(default=DEFAULT_PRINCIPAL, gt=0)
    start_date: date | None = None
    scenarios: list[RateScenarioRequest] | None = Field(default=None, max_length=6)
