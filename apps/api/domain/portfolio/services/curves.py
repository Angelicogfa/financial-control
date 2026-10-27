"""Load persisted BCB series into canonical `RateCurves` for fixed income valuation."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from core.helpers.units import daily_rates, monthly_rates
from domain.portfolio.services.fixed_income import RateCurves
from domain.portfolio.services.treasury_rates import IPCA_HISTORY_START
from domain.shared.entities import AssetEntity
from domain.shared.repositories import AbstractMarketSeriesRepository


def earliest_fixed_income_start(assets: Iterable[AssetEntity]) -> date | None:
    """Earliest date any fixed income lot starts accruing (its first purchase)."""
    starts = [
        tx.trade_date
        for asset in assets
        if asset.fixed_income_term is not None
        for tx in asset.transactions
    ]
    return min(starts) if starts else None


def load_rate_curves(
    series: AbstractMarketSeriesRepository,
    *,
    date_from: date | None,
    date_to: date,
    annual_cdi_rate: float,
    annual_ipca_rate: float,
) -> RateCurves:
    """Read CDI/SELIC daily and IPCA monthly series for (date_from, date_to] as fractions.

    IPCA is read from July 2000 on: the Tesouro IPCA+ VNA compounds it from its base date.
    """
    if date_from is None:
        return RateCurves(annual_cdi_rate=annual_cdi_rate, annual_ipca_rate=annual_ipca_rate)
    ipca_from = min(date(date_from.year, date_from.month, 1), IPCA_HISTORY_START)
    return RateCurves(
        cdi_daily=daily_rates(series.list_series("CDI", date_from=date_from, date_to=date_to)),
        selic_daily=daily_rates(series.list_series("SELIC", date_from=date_from, date_to=date_to)),
        ipca_monthly=monthly_rates(
            series.list_series("IPCA", date_from=ipca_from, date_to=date_to)
        ),
        annual_cdi_rate=annual_cdi_rate,
        annual_ipca_rate=annual_ipca_rate,
    )
