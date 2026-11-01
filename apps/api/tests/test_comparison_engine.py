"""Live scoreboard (Phase 45.8a): mirrored flow, strategies, engine and measures."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from domain.comparison.engine import (
    Book,
    Market,
    invest,
    replay_actual,
    run_strategy,
    targets_of,
    valuation_days,
    withdraw,
)
from domain.comparison.flow import ActualTrade, arca_flows, arca_trades
from domain.comparison.metrics import (
    rank_among,
    since,
    summarize,
    verdict_ready,
)
from domain.comparison.strategies import (
    AllCdi,
    Candidate,
    CerradoRule,
    EqualWeights,
    IndexArca,
    RandomPicks,
    RecommendationRuns,
)
from domain.shared.entities import AssetEntity, TransactionEntity
from domain.shared.enums import ArcaClass, AssetPurpose, AssetType, TransactionKind
from domain.simulation.data import CDI_KEY, IBOV_KEY
from domain.simulation.market import MarketHistory, PriceSeries

START = date(2024, 1, 1)
ACOES_ONLY = {ArcaClass.ACOES: 100.0}


def _daily(start: date, days: int, first: float, growth: float) -> PriceSeries:
    return PriceSeries.from_points(
        [(start + timedelta(days=i), first * (1.0 + growth) ** i) for i in range(days)]
    )


def _market(series: dict[str, PriceSeries], **kwargs) -> Market:
    return Market(history=MarketHistory(series=series), **kwargs)


def _flat(value: float = 10.0) -> PriceSeries:
    return _daily(START, 800, value, 0.0)


def _tx(kind: TransactionKind, day: date, qty: str, price: str) -> TransactionEntity:
    return TransactionEntity(
        asset_id=1, kind=kind, trade_date=day, quantity=Decimal(qty), unit_price=Decimal(price)
    )


def _asset(ticker: str, purpose: AssetPurpose, *txs: TransactionEntity) -> AssetEntity:
    return AssetEntity(
        ticker=ticker,
        name=ticker,
        asset_type=AssetType.STOCK_BR,
        arca_class=ArcaClass.ACOES,
        purpose=purpose,
        transactions=txs,
    )


# --- flow ---------------------------------------------------------------------------------------


def test_arca_flow_leaves_out_the_reserve_and_nets_each_day() -> None:
    day = date(2024, 2, 5)
    assets = [
        _asset(
            "AAAA3",
            AssetPurpose.ARCA,
            _tx(TransactionKind.BUY, day, "10", "10"),
            _tx(TransactionKind.SELL, day, "2", "10"),
            _tx(TransactionKind.BUY, date(2024, 3, 1), "5", "20"),
        ),
        _asset("RESV3", AssetPurpose.EMERGENCY_RESERVE, _tx(TransactionKind.BUY, day, "9", "9")),
    ]
    assert arca_flows(assets) == {day: 80.0, date(2024, 3, 1): 100.0}
    trades = arca_trades(assets)
    assert [t.quantity for t in trades] == [10.0, -2.0, 5.0]
    assert all(t.ticker == "AAAA3" for t in trades)


# --- strategies ---------------------------------------------------------------------------------


def test_equal_weights_split_the_class_among_assets_with_prices() -> None:
    late = PriceSeries.from_points([(date(2025, 1, 1), 5.0)])
    market = _market({"AAAA3": _flat(), "BBBB3": _flat(), "LATE3": late})
    universe = [
        Candidate(t, ArcaClass.ACOES, AssetType.STOCK_BR) for t in ("AAAA3", "BBBB3", "LATE3")
    ]
    holdings = EqualWeights(universe).decide(
        date(2024, 5, 10), market.history.view(date(2024, 5, 10))
    )
    assert holdings == {ArcaClass.ACOES: {"AAAA3": 0.5, "BBBB3": 0.5}}


def test_random_picks_repeat_within_the_quarter_and_differ_by_index() -> None:
    tickers = [f"T{i:02d}3" for i in range(20)]
    market = _market({t: _flat() for t in tickers})
    universe = [Candidate(t, ArcaClass.ACOES, AssetType.STOCK_BR) for t in tickers]
    view = market.history.view(date(2024, 6, 28))
    a = RandomPicks(universe, index=0).decide(date(2024, 5, 2), view)
    assert a == RandomPicks(universe, index=0).decide(date(2024, 6, 28), view)
    assert len(a[ArcaClass.ACOES]) == 5
    draws = {
        tuple(
            sorted(RandomPicks(universe, index=i).decide(date(2024, 5, 2), view)[ArcaClass.ACOES])
        )
        for i in range(10)
    }
    assert len(draws) > 1


def test_cerrado_rule_weights_by_score_and_index_uses_the_class_index() -> None:
    market = _market({"AAAA3": _flat(), "BBBB3": _flat(), IBOV_KEY: _flat(), CDI_KEY: _flat(1.0)})
    universe = [Candidate(t, ArcaClass.ACOES, AssetType.STOCK_BR) for t in ("AAAA3", "BBBB3")]
    view = market.history.view(date(2024, 4, 30))
    rule = CerradoRule(universe, scores=lambda day: {"AAAA3": 6.0, "BBBB3": 2.0})
    assert rule.decide(date(2024, 4, 30), view) == {ArcaClass.ACOES: {"AAAA3": 0.75, "BBBB3": 0.25}}
    index = IndexArca().decide(date(2024, 4, 30), view)
    assert index[ArcaClass.ACOES] == {IBOV_KEY: 1.0}
    assert index[ArcaClass.CAIXA] == {CDI_KEY: 1.0}
    assert AllCdi().class_targets({ArcaClass.ACOES: 60.0, ArcaClass.CAIXA: 40.0}) == {
        ArcaClass.CAIXA: 1.0
    }


def test_recommendation_follows_the_latest_run_and_waits_for_the_first() -> None:
    market = _market({"AAAA3": _flat()})
    runs = RecommendationRuns(
        [
            (date(2024, 3, 1), {ArcaClass.ACOES: {"AAAA3": 1.0}}),
            (date(2024, 2, 1), {ArcaClass.ACOES: {"BBBB3": 1.0}}),
        ]
    )
    view = market.history.view(date(2024, 3, 15))
    assert runs.first_day == date(2024, 2, 1)
    assert runs.decide(date(2024, 1, 15), view) is None
    assert runs.decide(date(2024, 2, 20), view) == {ArcaClass.ACOES: {"BBBB3": 1.0}}
    assert runs.decide(date(2024, 3, 15), view) == {ArcaClass.ACOES: {"AAAA3": 1.0}}


def test_an_empty_class_is_held_in_the_cdi() -> None:
    shares = {ArcaClass.ACOES: 0.6, ArcaClass.CAIXA: 0.4}
    assert targets_of({ArcaClass.ACOES: {"AAAA3": 1.0}}, shares) == {"AAAA3": 0.6, CDI_KEY: 0.4}


# --- engine -------------------------------------------------------------------------------------


def test_cdi_only_grows_the_contributions_by_the_cdi() -> None:
    market = _market({CDI_KEY: _daily(START, 800, 1.0, 0.0004)}, fee_rate=0.0)
    flows = {date(2024, 1, 10): 1000.0, date(2024, 2, 9): 500.0}
    days = valuation_days(list(flows), date(2024, 1, 10), date(2024, 3, 29))
    points, book = run_strategy(AllCdi(), market, flows, days, ACOES_ONLY)
    assert points[-1].contributed == 1500.0
    expected = (
        1000.0 * 1.0004 ** (date(2024, 3, 28) - date(2024, 1, 10)).days
        + 500.0 * 1.0004 ** (date(2024, 3, 28) - date(2024, 2, 9)).days
    )
    assert points[-1].value == pytest.approx(expected, abs=0.01)
    assert book.cash == pytest.approx(0.0, abs=0.01)


def test_whole_lots_leave_the_change_in_cash() -> None:
    market = _market(
        {"AAAA3": _flat(30.0), CDI_KEY: _flat(1.0)},
        lot_prices={"AAAA3": _flat(30.0)},
        asset_types={"AAAA3": AssetType.STOCK_BR},
    )
    universe = [Candidate("AAAA3", ArcaClass.ACOES, AssetType.STOCK_BR)]
    flows = {date(2024, 1, 10): 100.0}
    points, book = run_strategy(
        EqualWeights(universe), market, flows, [date(2024, 1, 10)], ACOES_ONLY
    )
    assert book.units["AAAA3"] == pytest.approx(3.0)  # 3 lots of R$ 30
    assert book.cash == pytest.approx(100.0 - 90.0 * 1.0003, abs=1e-6)
    assert points[-1].value == pytest.approx(100.0 - 90.0 * 0.0003, abs=0.01)


def test_contributions_go_to_the_asset_furthest_below_target() -> None:
    market = _market({"AAAA3": _flat(), "BBBB3": _flat(), CDI_KEY: _flat(1.0)}, fee_rate=0.0)
    book = Book(units={"AAAA3": 10.0}, cash=100.0)  # 100 in A, 100 cash: B is 100 below
    view = market.history.view(date(2024, 1, 10))
    invest(book, market, view, {"AAAA3": 0.5, "BBBB3": 0.5})
    assert book.units["BBBB3"] == pytest.approx(10.0)
    assert book.units["AAAA3"] == pytest.approx(10.0)


def test_withdrawals_use_cash_then_sell_with_the_tax_of_the_asset() -> None:
    day = date(2024, 6, 3)
    market = _market(
        {"AAAA3": _flat(20.0), "FIII11": _flat(20.0), CDI_KEY: _flat(1.0)},
        fee_rate=0.0,
        asset_types={"AAAA3": AssetType.STOCK_BR, "FIII11": AssetType.FII},
    )
    view = market.history.view(day)
    book = Book(
        units={"AAAA3": 50.0, "FIII11": 50.0},  # 1000 each, bought for 500 each
        cost={"AAAA3": 500.0, "FIII11": 500.0},
        first_buy={"AAAA3": START, "FIII11": START},
        cash=100.0,
    )
    withdraw(book, market, view, 1100.0)
    assert book.cash == pytest.approx(0.0, abs=0.05)
    # Stocks sold under R$ 20 mil in the month are exempt; the FII pays 20% on the gain.
    assert book.taxes > 0
    fii_gain = 500.0 * 0.5
    assert book.taxes == pytest.approx(fii_gain * 0.2, rel=0.15)
    assert book.value(view) == pytest.approx(2100.0 - 1100.0 - book.taxes, abs=0.1)


def test_running_in_two_parts_matches_one_run() -> None:
    market = _market(
        {"AAAA3": _daily(START, 800, 10.0, 0.0005), CDI_KEY: _daily(START, 800, 1.0, 0.0003)}
    )
    universe = [Candidate("AAAA3", ArcaClass.ACOES, AssetType.STOCK_BR)]
    flows = {date(2024, 1, 10): 1000.0, date(2024, 4, 10): 800.0, date(2024, 8, 12): -300.0}
    days = valuation_days(list(flows), date(2024, 1, 10), date(2024, 12, 31))
    whole, _ = run_strategy(EqualWeights(universe), market, flows, days, ACOES_ONLY)
    first, book = run_strategy(EqualWeights(universe), market, flows, days[:5], ACOES_ONLY)
    restored = Book.from_dict(book.to_dict())
    rest, _ = run_strategy(EqualWeights(universe), market, flows, days, ACOES_ONLY, book=restored)
    assert [p.value for p in first + rest] == [p.value for p in whole]


def test_a_strategy_that_mirrors_the_portfolio_reproduces_its_curve() -> None:
    series = _daily(START, 800, 10.0, 0.0007)
    market = _market({"AAAA3": series, CDI_KEY: _flat(1.0)}, fee_rate=0.0)
    trades = [
        ActualTrade(date(2024, 1, 10), "AAAA3", ArcaClass.ACOES, AssetType.STOCK_BR, 1000.0, 100.0),
        ActualTrade(date(2024, 3, 11), "AAAA3", ArcaClass.ACOES, AssetType.STOCK_BR, 500.0, 40.0),
    ]
    flows = {t.day: t.amount for t in trades}
    days = valuation_days(list(flows), date(2024, 1, 10), date(2024, 9, 30))
    yours, _, shares = replay_actual(trades, market, days)
    universe = [Candidate("AAAA3", ArcaClass.ACOES, AssetType.STOCK_BR)]
    mirror, _ = run_strategy(EqualWeights(universe), market, flows, days, ACOES_ONLY)
    assert [p.value for p in yours] == pytest.approx([p.value for p in mirror], abs=0.02)
    assert shares == {"AAAA3": 140.0}


def test_a_real_sale_takes_its_share_of_the_units() -> None:
    market = _market({"AAAA3": _flat(10.0), CDI_KEY: _flat(1.0)})
    trades = [
        ActualTrade(date(2024, 1, 10), "AAAA3", ArcaClass.ACOES, AssetType.STOCK_BR, 1000.0, 100.0),
        ActualTrade(date(2024, 2, 9), "AAAA3", ArcaClass.ACOES, AssetType.STOCK_BR, -250.0, -25.0),
    ]
    points, _, shares = replay_actual(trades, market, [date(2024, 1, 10), date(2024, 2, 9)])
    assert points[-1].value == pytest.approx(750.0)
    assert points[-1].contributed == 750.0
    assert shares["AAAA3"] == 75.0


def test_an_asset_without_series_is_valued_by_the_cdi() -> None:
    market = _market({CDI_KEY: _daily(START, 800, 1.0, 0.0004)})
    trades = [
        ActualTrade(date(2024, 1, 10), "TESOURO", ArcaClass.CAIXA, AssetType.TREASURY, 1000.0, 1.0)
    ]
    points, _, _ = replay_actual(trades, market, [date(2024, 1, 10), date(2024, 2, 9)])
    assert points[-1].value == pytest.approx(1000.0 * 1.0004**30, rel=1e-6)


def test_the_recommendation_starts_with_the_patrimony_of_the_day() -> None:
    market = _market({"AAAA3": _flat(), CDI_KEY: _flat(1.0)}, fee_rate=0.0)
    runs = RecommendationRuns([(date(2024, 3, 1), {ArcaClass.ACOES: {"AAAA3": 1.0}})])
    flows = {date(2024, 1, 10): 1000.0, date(2024, 4, 10): 200.0}
    days = [
        d
        for d in valuation_days(list(flows), date(2024, 1, 10), date(2024, 4, 30))
        if d >= date(2024, 3, 1)
    ]
    points, _ = run_strategy(runs, market, flows, days, ACOES_ONLY, initial=1000.0)
    assert points[0].day == date(2024, 3, 28)  # Good Friday on the 29th
    assert points[0].flow == 1000.0
    assert points[-1].contributed == 1200.0


# --- measures -----------------------------------------------------------------------------------


def test_rank_counts_the_random_portfolios_beaten() -> None:
    rank = rank_among(0.10, [0.05, 0.08, 0.12, None, 0.02])
    assert rank is not None
    assert (rank.portfolios, rank.beaten, rank.share) == (4, 3, 0.75)
    assert rank.low < 0.75 < rank.high
    assert rank_among(None, [0.1]) is None


def test_summary_and_the_prospective_part() -> None:
    market = _market({CDI_KEY: _daily(START, 800, 1.0, 0.0004)}, fee_rate=0.0)
    flows = {date(2024, 1, 10): 1000.0}
    days = valuation_days(list(flows), date(2024, 1, 10), date(2024, 12, 31))
    points, _ = run_strategy(AllCdi(), market, flows, days, ACOES_ONLY)
    whole = summarize(points)
    assert whole is not None
    assert whole.irr == pytest.approx(1.0004**365 - 1.0, rel=1e-3)
    assert whole.max_drawdown == 0.0
    part = since(points, date(2024, 7, 1))
    june = [p for p in points if p.day < date(2024, 7, 1)][-1]
    assert (part[0].day, part[0].flow) == (june.day, june.value)  # June's close enters as money in
    later = summarize(points, date(2024, 7, 1))
    assert later is not None and later.irr == pytest.approx(whole.irr, rel=1e-3)
    assert not verdict_ready(date(2024, 7, 1), date(2025, 6, 1))
    assert verdict_ready(date(2024, 7, 1), date(2025, 7, 1))
