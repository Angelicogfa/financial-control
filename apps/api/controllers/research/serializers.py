"""Domain entity to DTO serializers for the research module.

Scope: B3 catalog screener and watchlist.
"""

from __future__ import annotations

from dataclasses import asdict

from controllers.research.responses import (
    AssetComparisonDTO,
    AssetHistoryDTO,
    ComparedAssetDTO,
    ComparisonGroupDTO,
    ComparisonIndicatorDTO,
    ComparisonRowDTO,
    ScreenerItemDTO,
    TreasuryBondDTO,
)
from domain.assets.services.history import FundamentalPeriod
from domain.market.entities import TreasuryBond
from domain.research.services.comparison import GROUP_LABELS, INDICATORS, AssetComparison
from domain.research.services.screener import ScreenerResult
from domain.shared.enums import AssetType, default_arca_class


def to_screener_item_dto(result: ScreenerResult) -> ScreenerItemDTO:
    item, fund, valuation = result.instrument, result.fundamentals, result.valuation
    asset_type = item.asset_type or AssetType.STOCK_BR
    return ScreenerItemDTO(
        ticker=item.ticker,
        name=item.name,
        asset_type=asset_type,
        arca_class=default_arca_class(asset_type),
        sector=item.sector,
        close=item.close,
        change_pct=item.change_pct,
        volume_brl=item.volume_brl,
        market_cap=item.market_cap,
        logo_url=item.logo_url,
        price_to_earnings=fund.price_to_earnings if fund else None,
        price_to_book=fund.price_to_book if fund else None,
        dividend_yield=fund.dividend_yield if fund else None,
        return_on_equity=fund.return_on_equity if fund else None,
        valuation_verdict=valuation.verdict.value if valuation else None,
        fair_value=valuation.fair_value if valuation else None,
        margin=valuation.margin if valuation else None,
        asset_id=result.asset_id,
        lifecycle_status=result.lifecycle_status,
    )


def to_treasury_bond_dto(bond: TreasuryBond, *, asset_id: int | None = None) -> TreasuryBondDTO:
    return TreasuryBondDTO(
        symbol=bond.symbol,
        name=bond.name,
        bond_type=bond.bond_type,
        instrument_kind=bond.instrument_kind,
        indexer=bond.indexer,
        raw_indexer=bond.raw_indexer,
        coupon_type=bond.coupon_type,
        maturity_date=bond.maturity_date,
        duration_days=bond.duration_days,
        base_date=bond.base_date,
        buy_rate=bond.buy_rate,
        sell_rate=bond.sell_rate,
        buy_price=bond.buy_price,
        sell_price=bond.sell_price,
        base_price=bond.base_price,
        rate_type=bond.rate_type,
        rate_unit=bond.rate_unit,
        rate_description=bond.rate_description,
        contracted_rate_percent=bond.contracted_rate_percent,
        liquidity=bond.liquidity,
        asset_id=asset_id,
    )


def to_asset_comparison_dto(comparison: AssetComparison) -> AssetComparisonDTO:
    return AssetComparisonDTO(
        assets=[
            ComparedAssetDTO(
                ticker=a.ticker,
                name=a.name,
                asset_type=a.asset_type,
                profile=a.profile,
                asset_id=a.asset_id,
                currency=a.currency,
                price=a.price,
                valuation_verdict=a.valuation_verdict,
                fair_value=a.fair_value,
                margin_of_safety=a.margin_of_safety,
                checklist_score=a.checklist_score,
                checklist_max_score=a.checklist_max_score,
                checklist_normalized_score=a.checklist_normalized_score,
                checklist_coverage_pct=a.checklist_coverage_pct,
                checklist_recommendation=a.checklist_recommendation,
                statement_years=sum(
                    1 for s in a.statements if s.period == FundamentalPeriod.ANNUAL
                ),
            )
            for a in comparison.assets
        ],
        rows=[ComparisonRowDTO.model_validate(asdict(r)) for r in comparison.rows],
        history=[AssetHistoryDTO.model_validate(asdict(h)) for h in comparison.history],
        warnings=comparison.warnings,
        groups=[ComparisonGroupDTO(group=g, label=label) for g, label in GROUP_LABELS.items()],
        indicators=[
            ComparisonIndicatorDTO(
                key=i.key, label=i.label, group=i.group, unit=i.unit, better=i.better
            )
            for i in INDICATORS
        ],
    )
