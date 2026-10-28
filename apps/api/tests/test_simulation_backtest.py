"""Phase 33.2: strategy backtest engine — known-truth and look-ahead tests (design 8.2)."""

from __future__ import annotations

from datetime import date

import pytest

from domain.policy.services.policy import ArcaPolicy, ClassPolicy, InvestmentPolicy
from domain.shared.enums import ArcaClass, AssetType
from domain.simulation.engine import (
    BacktestConfig,
    SimulatedAsset,
    money_weighted_return,
    run_backtest,
    run_benchmark,
)
from domain.simulation.market import (
    LookAheadError,
    MarketHistory,
    PriceSeries,
    accumulate_rate_index,
    month_ends,
)

START = date(2025, 1, 1)
END = date(2025, 12, 31)
DAYS = month_ends(START, END)


def _policy(**targets: float) -> InvestmentPolicy:
    weights = {c: targets.get(c.value, 0.0) for c in ArcaClass}
    return InvestmentPolicy(
        arca=ArcaPolicy({c: ClassPolicy(target_pct=w) for c, w in weights.items()})
    )


def _growing(rate: float, start: float = 100.0, days: list[date] = DAYS) -> PriceSeries:
    return PriceSeries.from_points([(d, start * (1.0 + rate) ** i) for i, d in enumerate(days)])


def _intl(ticker: str, arca_class: ArcaClass = ArcaClass.ATIVOS_INTERNACIONAIS) -> SimulatedAsset:
    return SimulatedAsset(ticker, ticker, AssetType.STOCK_INTL, arca_class)


# --- market view ---


def test_month_ends_are_business_days_one_per_month() -> None:
    assert len(DAYS) == 12
    assert all(d.weekday() < 5 for d in DAYS)
    assert DAYS[0] == date(2025, 1, 31)
    assert DAYS[4] == date(2025, 5, 30)  # 31/05/2025 is a Saturday


def test_point_in_time_view_refuses_the_future() -> None:
    history = MarketHistory({"X": _growing(0.01)}, ipca_monthly={(2025, 6): 0.004})
    view = history.view(DAYS[2])
    assert view.price("X") == pytest.approx(100 * 1.01**2)
    assert view.price("X", DAYS[0]) == pytest.approx(100.0)
    with pytest.raises(LookAheadError):
        view.price("X", DAYS[3])
    with pytest.raises(LookAheadError):
        view.ipca(2025, 6)
    assert view.available("X") is True
    assert history.view(date(2024, 12, 31)).available("X") is False


def test_rate_index_accumulates_daily_rates() -> None:
    index = accumulate_rate_index([(date(2025, 1, 2), 1.0), (date(2025, 1, 3), 1.0)])
    assert index.prices[-1] == pytest.approx(1.01**2)


# --- known truths ---


def test_constant_growth_matches_the_annuity_formula() -> None:
    history = MarketHistory({"X": _growing(0.01)})
    config = BacktestConfig(START, END, monthly_contribution=1000.0, fee_rate=0.0, cash_symbol=None)

    result = run_backtest([_intl("X")], history, _policy(ATIVOS_INTERNACIONAIS=100.0), config)

    expected = 1000.0 * ((1.01**12 - 1.0) / 0.01)
    assert result.summary.final_value == pytest.approx(expected, abs=0.05)
    assert result.summary.contributed == 12_000.0
    assert result.summary.time_weighted_return == pytest.approx(1.01**11 - 1.0, abs=1e-5)
    assert result.summary.money_weighted_return == pytest.approx(1.01**12 - 1.0, abs=2e-3)
    assert result.summary.trades == 12


def test_benchmark_with_the_same_flow_matches_the_single_asset_strategy() -> None:
    history = MarketHistory({"X": _growing(0.01)})
    config = BacktestConfig(START, END, monthly_contribution=1000.0, fee_rate=0.0, cash_symbol=None)
    strategy = run_backtest([_intl("X")], history, _policy(ATIVOS_INTERNACIONAIS=100.0), config)
    benchmark = run_benchmark("X", history, config)
    assert benchmark.summary.final_value == pytest.approx(strategy.summary.final_value, abs=0.05)


def test_full_cdi_portfolio_reproduces_the_cdi_benchmark() -> None:
    daily = [(d, 0.04) for d in DAYS]  # one rate point per month end is enough for the test
    cdi = accumulate_rate_index(daily)
    history = MarketHistory({"CDI": cdi})
    config = BacktestConfig(START, END, monthly_contribution=500.0, fee_rate=0.0, cash_symbol="CDI")
    caixa = SimulatedAsset(
        "CAIXA", "Caixa CDI", AssetType.CASH, ArcaClass.CAIXA, price_symbol="CDI"
    )

    strategy = run_backtest([caixa], history, _policy(CAIXA=100.0), config)
    benchmark = run_benchmark("CDI", history, config)

    assert strategy.summary.final_value == pytest.approx(benchmark.summary.final_value, abs=0.05)


def test_equal_returns_keep_the_target_weights() -> None:
    assets = [
        _intl("A", ArcaClass.ACOES),
        _intl("R", ArcaClass.REAL_ESTATE),
        _intl("C", ArcaClass.CAIXA),
        _intl("I", ArcaClass.ATIVOS_INTERNACIONAIS),
    ]
    history = MarketHistory({a.ticker: _growing(0.005) for a in assets})
    config = BacktestConfig(START, END, monthly_contribution=4000.0, fee_rate=0.0, cash_symbol=None)
    policy = _policy(ACOES=25.0, REAL_ESTATE=25.0, CAIXA=25.0, ATIVOS_INTERNACIONAIS=25.0)

    result = run_backtest(assets, history, policy, config)

    last = result.points[-1]
    total = sum(last.by_class.values())
    for value in last.by_class.values():
        assert value / total == pytest.approx(0.25, abs=1e-4)


def test_integer_lots_leave_cash_for_the_next_month() -> None:
    days = DAYS[:3]
    history = MarketHistory({"WEGE3": PriceSeries.from_points([(d, 30.0) for d in days])})
    config = BacktestConfig(
        START, days[-1], monthly_contribution=100.0, fee_rate=0.0, cash_symbol=None
    )
    asset = SimulatedAsset("WEGE3", "WEG", AssetType.STOCK_BR, ArcaClass.ACOES)

    result = run_backtest([asset], history, _policy(ACOES=100.0), config)

    # 100 -> 3 units (90) + 10; 110 -> 3 units + 20; 120 -> 4 units + 0.
    assert [p.cash for p in result.points] == [10.0, 20.0, 0.0]
    assert result.summary.final_value == 300.0


def test_fees_reduce_the_result() -> None:
    history = MarketHistory({"X": _growing(0.01)})
    free = BacktestConfig(START, END, monthly_contribution=1000.0, fee_rate=0.0, cash_symbol=None)
    paid = BacktestConfig(START, END, monthly_contribution=1000.0, fee_rate=0.001, cash_symbol=None)
    policy = _policy(ATIVOS_INTERNACIONAIS=100.0)

    a = run_backtest([_intl("X")], history, policy, free).summary
    b = run_backtest([_intl("X")], history, policy, paid).summary

    assert b.fees > 0
    assert b.final_value < a.final_value


def test_contributions_grow_with_the_previous_month_ipca() -> None:
    history = MarketHistory(
        {"X": _growing(0.0)},
        ipca_monthly={(d.year, d.month): 0.01 for d in DAYS},
    )
    config = BacktestConfig(
        START,
        END,
        monthly_contribution=1000.0,
        correct_by_ipca=True,
        fee_rate=0.0,
        cash_symbol=None,
    )
    result = run_backtest([_intl("X")], history, _policy(ATIVOS_INTERNACIONAIS=100.0), config)
    assert [p.contribution for p in result.points[:3]] == [1000.0, 1010.0, 1020.1]


def test_asset_enters_only_after_its_first_price() -> None:
    history = MarketHistory(
        {
            "OLD": _growing(0.0),
            "NEW": PriceSeries.from_points([(d, 50.0) for d in DAYS[6:]]),
        }
    )
    config = BacktestConfig(START, END, monthly_contribution=1000.0, fee_rate=0.0, cash_symbol=None)
    assets = [_intl("OLD"), _intl("NEW"), _intl("NEVER")]

    result = run_backtest(assets, history, _policy(ATIVOS_INTERNACIONAIS=100.0), config)

    assert result.unavailable == ["NEVER"]
    assert result.points[5].market_value == pytest.approx(6000.0, abs=0.05)
    assert result.points[-1].market_value == pytest.approx(12_000.0, abs=0.05)


# --- look-ahead ---


def test_future_prices_never_change_the_past() -> None:
    clean = _growing(0.01)
    poisoned = PriceSeries.from_points(
        [
            (d, p * (100.0 if i >= 6 else 1.0))
            for i, (d, p) in enumerate(zip(clean.dates, clean.prices, strict=True))
        ]
    )
    config = BacktestConfig(START, END, monthly_contribution=1000.0, fee_rate=0.0, cash_symbol=None)
    policy = _policy(ATIVOS_INTERNACIONAIS=100.0)

    a = run_backtest([_intl("X")], MarketHistory({"X": clean}), policy, config)
    b = run_backtest([_intl("X")], MarketHistory({"X": poisoned}), policy, config)
    short = run_backtest(
        [_intl("X")],
        MarketHistory({"X": clean}),
        policy,
        BacktestConfig(START, DAYS[5], 1000.0, fee_rate=0.0, cash_symbol=None),
    )

    assert a.points[:6] == b.points[:6]
    assert a.points[:6] == short.points


def test_money_weighted_return_of_a_doubling() -> None:
    assert money_weighted_return(
        [(date(2025, 1, 1), 1000.0)], (date(2026, 1, 1), 2000.0)
    ) == pytest.approx(1.0, abs=1e-4)
    assert money_weighted_return([], (date(2026, 1, 1), 2000.0)) is None
