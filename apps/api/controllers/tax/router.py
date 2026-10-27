"""HTTP controllers (routers) of the tax module; they only delegate to use cases.

Scope: tax rule registry, per-asset tax status and the fixed income comparator.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from controllers.tax.dependencies import get_tax_handler
from controllers.tax.requests import FixedIncomeCompareRequest
from controllers.tax.responses import AssetTaxStatusDTO, FixedIncomeComparisonDTO, TaxRuleDTO
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
