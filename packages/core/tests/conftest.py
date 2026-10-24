"""Shared fixtures for `packages/core` tests: the reference portfolio (golden inputs)."""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fincontrol_core.arca.allocation import ArcaTargets
from fincontrol_core.domain.entities import (
    AssetEntity,
    EarningEntity,
    FixedIncomeTermEntity,
    MarketSeriesPoint,
    TransactionEntity,
)
from fincontrol_core.domain.enums import (
    AssetType,
    EarningKind,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    SeriesUnit,
    TransactionKind,
)
from fincontrol_core.market.models import Quote
from fincontrol_core.market.units import daily_rates, monthly_rates
from fincontrol_core.portfolio.consolidation import (
    ConsolidatedPortfolioReport,
    consolidate_portfolio,
)
from fincontrol_core.portfolio.fixed_income import RateCurves

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


def _load_reference_data() -> dict[str, Any]:
    return json.loads((GOLDEN_DIR / "reference_portfolio.json").read_text(encoding="utf-8"))


def _rate_curves(data: dict[str, Any]) -> RateCurves:
    """Build curves from BCB-style percentage points (one CDI point per business day)."""
    holidays = {date.fromisoformat(h) for h in data["holidays"]}
    months = sorted(data["cdi_daily_pct_by_month"])
    current = date.fromisoformat(f"{months[0]}-01")
    end = date.fromisoformat(data["as_of_date"])
    cdi_points: list[MarketSeriesPoint] = []
    while current <= end:
        if current.weekday() < 5 and current not in holidays:
            pct = data["cdi_daily_pct_by_month"][current.strftime("%Y-%m")]
            cdi_points.append(
                MarketSeriesPoint("CDI", current, pct, unit=SeriesUnit.PERCENT_PER_DAY)
            )
        current += timedelta(days=1)
    ipca_points = [
        MarketSeriesPoint(
            "IPCA", date.fromisoformat(f"{month}-01"), pct, unit=SeriesUnit.PERCENT_PER_MONTH
        )
        for month, pct in data["ipca_monthly_pct"].items()
    ]
    return RateCurves(
        cdi_daily=daily_rates(cdi_points),
        ipca_monthly=monthly_rates(ipca_points),
        annual_cdi_rate=data["annual_cdi_rate_fallback"],
        annual_ipca_rate=data["annual_ipca_rate_fallback"],
    )


def _build_asset(raw: dict[str, Any]) -> AssetEntity:
    asset_id = raw["id"]
    transactions = tuple(
        TransactionEntity(
            asset_id=asset_id,
            kind=TransactionKind(tx["kind"]),
            trade_date=date.fromisoformat(tx["date"]),
            quantity=Decimal(tx["qty"]),
            unit_price=Decimal(tx["price"]),
            fees=Decimal(tx["fees"]),
            fx_rate=Decimal(tx["fx"]),
            id=asset_id * 100 + index,
        )
        for index, tx in enumerate(raw["transactions"])
    )
    earnings = tuple(
        EarningEntity(
            asset_id=asset_id,
            kind=EarningKind(e["kind"]),
            payment_date=date.fromisoformat(e["date"]),
            gross_amount=Decimal(e["gross"]),
            withholding_tax=Decimal(e["tax"]),
        )
        for e in raw["earnings"]
    )
    term = None
    if raw_term := raw.get("fixed_income_term"):
        term = FixedIncomeTermEntity(
            instrument_kind=FixedIncomeInstrumentKind(raw_term["instrument_kind"]),
            indexer=FixedIncomeIndexer(raw_term["indexer"]),
            contracted_rate=Decimal(raw_term["contracted_rate"]),
            issue_date=date.fromisoformat(raw_term["issue_date"]),
            tax_exempt=raw_term["tax_exempt"],
        )
    return AssetEntity(
        id=asset_id,
        ticker=raw["ticker"],
        name=raw["name"],
        asset_type=AssetType(raw["asset_type"]),
        use_cerrado=False,
        fixed_income_term=term,
        transactions=transactions,
        earnings=earnings,
    )


@pytest.fixture(scope="session")
def reference_portfolio_data() -> dict[str, Any]:
    """Raw inputs of the reference portfolio shared with build_reference_golden.py."""
    return _load_reference_data()


@pytest.fixture(scope="session")
def reference_assets(reference_portfolio_data: dict[str, Any]) -> list[AssetEntity]:
    return [_build_asset(raw) for raw in reference_portfolio_data["assets"]]


@pytest.fixture(scope="session")
def reference_report(
    reference_portfolio_data: dict[str, Any],
    reference_assets: list[AssetEntity],
) -> ConsolidatedPortfolioReport:
    data = reference_portfolio_data
    quotes = {
        raw["ticker"]: Quote(symbol=raw["ticker"], price=raw["quote"])
        for raw in data["assets"]
        if "quote" in raw
    }
    return consolidate_portfolio(
        reference_assets,
        ArcaTargets.default(),
        quotes=quotes,
        usd_brl_rate=data["usd_brl_rate"],
        curves=_rate_curves(data),
        as_of_date=date.fromisoformat(data["as_of_date"]),
    )
