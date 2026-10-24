"""Characterization tests for the 2026-10-24 systemic audit findings (pure domain).

Each test asserts the *correct* behavior and is marked `xfail(strict=True)` while the
defect exists. Fixing a finding makes its test pass, which turns the strict xfail into
a failure until the marker is removed — so no fix lands without its regression test.
Finding IDs (C-*, I-*, A-*) are listed in docs/todo/IMPLEMENTATION_PLAN.md.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import httpx
import pytest
from fincontrol_core.analytics import beta_alpha, time_weighted_return
from fincontrol_core.arca.allocation import ArcaTargets
from fincontrol_core.domain.entities import (
    AssetEntity,
    FixedIncomeTermEntity,
    MarketSeriesPoint,
    PortfolioSnapshotEntity,
    TransactionEntity,
)
from fincontrol_core.domain.enums import (
    ArcaClass,
    AssetType,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    IntraClassStrategy,
    SeriesUnit,
    TransactionKind,
)
from fincontrol_core.market.brapi import BrapiProvider
from fincontrol_core.market.models import Quote
from fincontrol_core.market.units import daily_rates
from fincontrol_core.portfolio.consolidation import consolidate_portfolio, plan_contribution
from fincontrol_core.portfolio.fixed_income import (
    RateCurves,
    count_business_days,
    value_fixed_income_position,
)


def _xfail(finding: str, description: str, raises: type[BaseException] = AssertionError):
    return pytest.mark.xfail(strict=True, raises=raises, reason=f"{finding}: {description}")


def _business_days(start: date, count: int) -> list[date]:
    days: list[date] = []
    current = start
    while len(days) < count:
        current += timedelta(days=1)
        if current.weekday() < 5:
            days.append(current)
    return days


def _cdi_term(issue: date, multiplier: str = "1.00") -> FixedIncomeTermEntity:
    return FixedIncomeTermEntity(
        instrument_kind=FixedIncomeInstrumentKind.CDB,
        indexer=FixedIncomeIndexer.CDI,
        contracted_rate=Decimal(multiplier),
        issue_date=issue,
    )


def _pre_term(issue: date, annual_rate: str) -> FixedIncomeTermEntity:
    return FixedIncomeTermEntity(
        instrument_kind=FixedIncomeInstrumentKind.CDB,
        indexer=FixedIncomeIndexer.PRE,
        contracted_rate=Decimal(annual_rate),
        issue_date=issue,
    )


def _buy(asset_id: int, on: date, qty: str, price: str, fx: str = "1") -> TransactionEntity:
    return TransactionEntity(
        asset_id=asset_id,
        kind=TransactionKind.BUY,
        trade_date=on,
        quantity=Decimal(qty),
        unit_price=Decimal(price),
        fx_rate=Decimal(fx),
    )


def _sell(asset_id: int, on: date, qty: str, price: str, fx: str = "1") -> TransactionEntity:
    return TransactionEntity(
        asset_id=asset_id,
        kind=TransactionKind.SELL,
        trade_date=on,
        quantity=Decimal(qty),
        unit_price=Decimal(price),
        fx_rate=Decimal(fx),
    )


# ---------------------------------------------------------------------------
# C-01 — BCB SGS 12 daily CDI is always a percentage per business day
# ---------------------------------------------------------------------------
def _accrue_cdi(daily_pct: float, days: int = 10) -> float:
    issue = date(2024, 3, 1)
    dates = _business_days(issue, days)
    # Points exactly as BCB SGS 12 returns them: percent per business day.
    points = [
        MarketSeriesPoint("CDI", d, daily_pct, unit=SeriesUnit.PERCENT_PER_DAY) for d in dates
    ]
    valuation = value_fixed_income_position(
        [_buy(1, issue, "1", "1000")],
        _cdi_term(issue),
        dates[-1],
        curves=RateCurves(cdi_daily=daily_rates(points)),
    )
    return valuation.gross_value


def test_c01_daily_cdi_above_heuristic_threshold_is_read_as_percentage() -> None:
    # 0.0551% per day (~14.9% a.a.) was above the old 0.05 threshold and always worked.
    assert _accrue_cdi(0.0551) == pytest.approx(1000 * (1 + 0.000551) ** 10, abs=0.01)


def test_c01_daily_cdi_below_heuristic_threshold_is_read_as_percentage() -> None:
    # 0.0393% per day (~10.4% a.a., 2024 levels) used to be read as 3.93% per day.
    assert _accrue_cdi(0.0393) == pytest.approx(1000 * (1 + 0.000393) ** 10, abs=0.01)


# ---------------------------------------------------------------------------
# C-02 — USD positions must keep historical FX for cost and realized P/L
# ---------------------------------------------------------------------------
def _usd_asset(transactions: tuple[TransactionEntity, ...]) -> AssetEntity:
    return AssetEntity(
        id=1,
        ticker="AAPL",
        name="Apple",
        asset_type=AssetType.STOCK_INTL,
        transactions=transactions,
    )


def _consolidate_usd(asset: AssetEntity, usd_brl: float):
    return consolidate_portfolio(
        [asset],
        ArcaTargets.default(),
        quotes={"AAPL": Quote(symbol="AAPL", price=100.0, currency="USD")},
        usd_brl_rate=usd_brl,
        as_of_date=date(2025, 6, 30),
    )


def test_c02_invested_value_uses_purchase_fx_and_shows_fx_gain() -> None:
    asset = _usd_asset((_buy(1, date(2025, 1, 10), "10", "100", fx="5.0"),))
    pos = _consolidate_usd(asset, usd_brl=6.0).positions[0]

    assert pos.invested_value_brl == pytest.approx(5000.0)
    assert pos.current_value_brl == pytest.approx(6000.0)
    assert pos.unrealized_pnl_brl == pytest.approx(1000.0)


def test_c02_realized_pnl_uses_trade_date_fx() -> None:
    asset = _usd_asset(
        (
            _buy(1, date(2025, 1, 10), "10", "100", fx="5.0"),
            _sell(1, date(2025, 3, 10), "5", "100", fx="6.0"),
        )
    )
    pos = _consolidate_usd(asset, usd_brl=5.5).positions[0]

    # Same USD price, but BRL proceeds 5 * 600 vs BRL cost 5 * 500.
    assert pos.realized_pnl_brl == pytest.approx(500.0)


# ---------------------------------------------------------------------------
# C-04 — Fixed income sells must reduce principal proportionally
# ---------------------------------------------------------------------------
def test_c04_fixed_income_sell_reduces_principal_proportionally() -> None:
    issue = date(2024, 1, 2)
    sell_day = date(2025, 1, 2)
    term = _pre_term(issue, "0.10")
    before = value_fixed_income_position([_buy(1, issue, "1", "1000")], term, sell_day)
    half_gross = Decimal(str(round(before.gross_value / 2, 2)))

    after = value_fixed_income_position(
        [_buy(1, issue, "1", "1000"), _sell(1, sell_day, "1", str(half_gross))],
        term,
        sell_day,
    )

    assert after.invested_principal == pytest.approx(500.0, abs=0.01)
    assert after.gross_value == pytest.approx(before.gross_value / 2, abs=0.02)


# ---------------------------------------------------------------------------
# I-01 — Business-day calendar and 12-month projection
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("start", "end"),
    [
        (date(2026, 4, 20), date(2026, 4, 21)),  # Tiradentes (Tuesday)
        (date(2026, 12, 24), date(2026, 12, 25)),  # Christmas (Friday)
        (date(2026, 2, 15), date(2026, 2, 17)),  # Carnival Monday and Tuesday
    ],
)
def test_i01_business_days_skip_national_holidays(start: date, end: date) -> None:
    assert count_business_days(start, end) == 0


def test_i01_projection_for_pre_fixed_rate_matches_one_year() -> None:
    issue = date(2027, 3, 1)
    as_of = date(2027, 9, 1)
    valuation = value_fixed_income_position(
        [_buy(1, issue, "1", "1000")], _pre_term(issue, "0.10"), as_of
    )
    # Net value one year (252 business days) ahead minus net value today. The yield accrued
    # by then is taxed at the bracket of the horizon: 184 + 365 = 549 days -> 17.5%.
    # (The original expectation of a flat 15% ignored the regressive table.)
    gross_in_one_year = valuation.gross_value * 1.10
    net_in_one_year = gross_in_one_year - (gross_in_one_year - 1000.0) * 0.175
    expected = net_in_one_year - valuation.net_value
    assert valuation.projected_12m_net_yield == pytest.approx(expected, abs=0.02)


# ---------------------------------------------------------------------------
# I-02 / I-10 — Provider fields must be converted by declared unit (ADR 0006)
# ---------------------------------------------------------------------------
def _brapi_fundamentals(item: dict) -> object:
    payload = {"results": [{"symbol": "TEST3", **item}]}
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _req: httpx.Response(200, json=payload))
    )
    fundamentals = BrapiProvider(client=client).get_fundamentals("TEST3")
    assert fundamentals is not None
    return fundamentals


def test_i02_roe_fraction_above_one_is_kept() -> None:
    fundamentals = _brapi_fundamentals({"financialData": {"returnOnEquity": {"raw": 1.6}}})
    assert fundamentals.return_on_equity == pytest.approx(1.6)


def test_i02_debt_to_equity_percentage_is_always_converted() -> None:
    fundamentals = _brapi_fundamentals({"financialData": {"debtToEquity": {"raw": 4.0}}})
    assert fundamentals.debt_to_equity == pytest.approx(0.04)


def test_i10_average_daily_volume_is_financial() -> None:
    fundamentals = _brapi_fundamentals(
        {"regularMarketPrice": 100.0, "averageDailyVolume10Day": 30_000}
    )
    assert fundamentals.avg_daily_volume == pytest.approx(3_000_000.0)


# ---------------------------------------------------------------------------
# I-09 — TWR must include income; beta must align returns by date
# ---------------------------------------------------------------------------
@_xfail("I-09", "TWR ignores earnings received between snapshots")
def test_i09_twr_counts_dividends_as_return() -> None:
    snapshots = [
        PortfolioSnapshotEntity(date(2025, 1, 2), 1000.0, 1000.0, 0.0, earnings_cum=0.0),
        PortfolioSnapshotEntity(date(2025, 1, 3), 1000.0, 1000.0, 0.0, earnings_cum=10.0),
    ]
    assert time_weighted_return(snapshots) == pytest.approx([0.01])


@_xfail("I-09", "beta_alpha has no date inputs and aligns series by array tail", TypeError)
def test_i09_beta_aligns_returns_by_date() -> None:
    # B3 is closed on 2025-01-03 (hypothetical), the benchmark is not.
    asset_dates = [date(2025, 1, 2), date(2025, 1, 6), date(2025, 1, 7)]
    bench_dates = [date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 6), date(2025, 1, 7)]
    asset_rets = [0.01, 0.02, -0.01]
    bench_rets = [0.01, 0.50, 0.02, -0.01]

    beta, _alpha = beta_alpha(
        asset_rets,
        bench_rets,
        asset_dates=asset_dates,
        benchmark_dates=bench_dates,
    )
    assert beta == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# A-04 — Contribution planner
# ---------------------------------------------------------------------------
def _stock(asset_id: int, ticker: str, weight: str | None = None) -> AssetEntity:
    return AssetEntity(
        id=asset_id,
        ticker=ticker,
        name=ticker,
        asset_type=AssetType.STOCK_BR,
        custom_class_weight=Decimal(weight) if weight is not None else None,
    )


def test_a04_manual_override_uses_custom_class_weight() -> None:
    assets = [_stock(1, "AAAA3", "80"), _stock(2, "BBBB3", "20")]
    quotes = {a.ticker: Quote(symbol=a.ticker, price=10.0) for a in assets}
    targets = ArcaTargets(
        {
            ArcaClass.ACOES: 100.0,
            ArcaClass.REAL_ESTATE: 0.0,
            ArcaClass.CAIXA: 0.0,
            ArcaClass.ATIVOS_INTERNACIONAIS: 0.0,
        }
    )
    report = consolidate_portfolio(
        assets,
        targets,
        quotes=quotes,
        intra_strategies={c: IntraClassStrategy.EQUAL_WEIGHT for c in ArcaClass},
        as_of_date=date(2025, 6, 30),
    )

    plan = plan_contribution(
        report, targets, 1000.0, strategy_override=IntraClassStrategy.MANUAL_WEIGHT
    )

    weights = {o.ticker: o.intra_class_target_weight_pct for o in plan.orders}
    assert weights == {"AAAA3": pytest.approx(80.0), "BBBB3": pytest.approx(20.0)}


def test_a04_rounding_leftover_flows_to_other_classes() -> None:
    stock = _stock(1, "PRIC3")
    cash = AssetEntity(
        id=2,
        ticker="CAIXA",
        name="Conta remunerada",
        asset_type=AssetType.CASH,
        manual_price=Decimal("1"),
    )
    targets = ArcaTargets(
        {
            ArcaClass.ACOES: 50.0,
            ArcaClass.REAL_ESTATE: 0.0,
            ArcaClass.CAIXA: 50.0,
            ArcaClass.ATIVOS_INTERNACIONAIS: 0.0,
        }
    )
    report = consolidate_portfolio(
        [stock, cash],
        targets,
        quotes={"PRIC3": Quote(symbol="PRIC3", price=300.0)},
        as_of_date=date(2025, 6, 30),
    )

    plan = plan_contribution(report, targets, 1000.0)

    # ACOES buys 1 share (R$ 300) out of R$ 500; the R$ 200 left must go to CAIXA.
    assert plan.unallocated_cash_brl < 1.0
