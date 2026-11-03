"""HTTP controllers (routers) of the tax module; they only delegate to use cases.

Scope: tax rule registry, per-asset tax status, the fixed income comparator and the monthly
income tax with its DARF (Phase 48.R7).
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from contracts.tax.requests import DarfPaymentRequest, FixedIncomeCompareRequest
from contracts.tax.responses import (
    AssetTaxStatusDTO,
    FixedIncomeComparisonDTO,
    TaxMonthDTO,
    TaxRuleDTO,
    TaxYearDTO,
)
from contracts.tax.serializers import to_tax_month_dto, to_tax_year_dto
from controllers.tax.dependencies import get_monthly_tax_handler, get_tax_handler
from domain.tax.services.monthly import MonthlyTaxHandler
from domain.tax.services.use_cases import TaxHandler

tax_router = APIRouter(prefix="/tax", tags=["Tax"])


@tax_router.get("/rules", response_model=list[TaxRuleDTO])
def list_tax_rules(handler: TaxHandler = Depends(get_tax_handler)) -> list[TaxRuleDTO]:
    """IR and IOF rules with their validity periods (vigência)."""
    return handler.list_rules()


@tax_router.get("/assets/{asset_id}/status", response_model=AssetTaxStatusDTO)
def get_asset_tax_status(
    asset_id: int,
    as_of_date: date | None = Query(default=None),
    handler: TaxHandler = Depends(get_tax_handler),
) -> AssetTaxStatusDTO:
    """Current bracket, next drop and estimated IR per lot (informative regime otherwise)."""
    return handler.asset_tax_status(asset_id, as_of_date=as_of_date)


@tax_router.post("/fixed-income/compare", response_model=FixedIncomeComparisonDTO)
def compare_fixed_income(
    payload: FixedIncomeCompareRequest,
    handler: TaxHandler = Depends(get_tax_handler),
) -> FixedIncomeComparisonDTO:
    """Taxed vs. exempt comparison: net value and rate, bracket equivalences, break-even."""
    return handler.compare_fixed_income(payload)


@tax_router.get("/monthly", response_model=TaxYearDTO)
def get_monthly_tax(
    year: int | None = Query(default=None, ge=2000),
    handler: MonthlyTaxHandler = Depends(get_monthly_tax_handler),
) -> TaxYearDTO:
    return to_tax_year_dto(handler.year(year or date.today().year))


@tax_router.get("/monthly/{month}", response_model=TaxMonthDTO)
def get_tax_month(
    month: str,
    handler: MonthlyTaxHandler = Depends(get_monthly_tax_handler),
) -> TaxMonthDTO:
    return to_tax_month_dto(handler.month(month))


@tax_router.put("/monthly/{month}/darf", response_model=TaxMonthDTO)
def mark_darf_paid(
    month: str,
    payload: DarfPaymentRequest,
    handler: MonthlyTaxHandler = Depends(get_monthly_tax_handler),
) -> TaxMonthDTO:
    return to_tax_month_dto(handler.set_paid(month, payload.paid_on))
