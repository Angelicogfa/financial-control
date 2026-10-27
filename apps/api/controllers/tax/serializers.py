"""Map pure tax domain results to response DTOs."""

from __future__ import annotations

from dataclasses import asdict

from controllers.tax.responses import (
    AssetTaxStatusDTO,
    BreakEvenDTO,
    FixedIncomeComparisonDTO,
    OfferProjectionDTO,
    RateScenarioDTO,
    ResolvedOfferDTO,
    TaxRuleDTO,
)
from domain.tax.entities import TaxRule
from domain.tax.services.comparator import FixedIncomeComparison, FixedIncomeOffer
from domain.tax.services.status import AssetTaxStatus


def to_tax_rule_dto(rule: TaxRule) -> TaxRuleDTO:
    return TaxRuleDTO(**asdict(rule))


def to_asset_tax_status_dto(status: AssetTaxStatus) -> AssetTaxStatusDTO:
    return AssetTaxStatusDTO(**asdict(status))


def to_comparison_dto(
    comparison: FixedIncomeComparison,
    offers: list[FixedIncomeOffer],
    asset_ids: list[int | None],
) -> FixedIncomeComparisonDTO:
    return FixedIncomeComparisonDTO(
        as_of_date=comparison.as_of_date,
        principal=comparison.principal,
        common_window_days=comparison.common_window_days,
        offers=[
            ResolvedOfferDTO(**asdict(offer), asset_id=asset_id)
            for offer, asset_id in zip(offers, asset_ids, strict=True)
        ],
        scenarios=[RateScenarioDTO(**asdict(s)) for s in comparison.scenarios],
        projections=[OfferProjectionDTO(**asdict(p)) for p in comparison.projections],
        break_evens=[BreakEvenDTO(**asdict(b)) for b in comparison.break_evens],
        best_by_scenario=dict(comparison.best_by_scenario),
    )
