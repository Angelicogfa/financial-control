"""Domain entity to DTO serializers for the research module.

Scope: B3 catalog screener and watchlist.
"""

from __future__ import annotations

from controllers.research.responses import ScreenerItemDTO
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
