"""Phase 33.2 (second part): rebalancing with income tax, policy by date, checklist history."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from domain.policy.services.policy import ArcaPolicy, ClassPolicy, InvestmentPolicy
from domain.shared.entities import ChecklistAnswer
from domain.shared.enums import AnswerSource, AnswerValue, ArcaClass, AssetType, ChecklistProfile
from domain.simulation.engine import (
    BacktestConfig,
    SimulatedAsset,
    answers_on,
    policy_on,
    run_backtest,
)
from domain.simulation.market import MarketHistory, PriceSeries, month_ends

START = date(2025, 1, 1)
END = date(2025, 3, 31)
DAYS = month_ends(START, date(2025, 12, 31))


def _policy(created: datetime | None = None, **targets: float) -> InvestmentPolicy:
    weights = {c: targets.get(c.value, 0.0) for c in ArcaClass}
    return InvestmentPolicy(
        arca=ArcaPolicy({c: ClassPolicy(target_pct=w) for c, w in weights.items()}),
        created_at=created,
    )


def _series(*prices: float) -> PriceSeries:
    return PriceSeries.from_points(list(zip(DAYS, prices, strict=False)))


def _config(initial: float, *, rebalance: bool = True, end: date = END) -> BacktestConfig:
    return BacktestConfig(
        START,
        end,
        monthly_contribution=0.0,
        initial_contribution=initial,
        fee_rate=0.0,
        cash_symbol=None,
        rebalance=rebalance,
    )


def _two_classes(asset_type: AssetType) -> list[SimulatedAsset]:
    return [
        SimulatedAsset("A", "A", asset_type, ArcaClass.ACOES),
        SimulatedAsset("C", "C", AssetType.STOCK_INTL, ArcaClass.CAIXA),
    ]


HISTORY = MarketHistory({"A": _series(100.0, 200.0, 200.0), "C": _series(100.0, 100.0, 100.0)})
HALF = _policy(ACOES=50.0, CAIXA=50.0)


def test_rebalancing_sells_the_excess_and_pays_the_tax() -> None:
    result = run_backtest(_two_classes(AssetType.STOCK_INTL), HISTORY, HALF, _config(10_000.0))

    # Month 2: A 10.000 (66,7%) x C 5.000 -> sell 2.500 of A (12,5 units, gain 1.250).
    # Foreign assets pay 15% on the gain: 187,50; the rest buys C.
    second = result.points[1]
    assert result.summary.sales == 1
    assert second.taxes == pytest.approx(187.5)
    assert second.by_class[ArcaClass.ACOES] == pytest.approx(7500.0)
    assert second.by_class[ArcaClass.CAIXA] == pytest.approx(7312.5)
    assert result.summary.taxes == pytest.approx(187.5)


def test_without_rebalancing_the_weights_drift() -> None:
    result = run_backtest(
        _two_classes(AssetType.STOCK_INTL), HISTORY, HALF, _config(10_000.0, rebalance=False)
    )
    assert result.summary.sales == 0
    assert result.points[-1].by_class[ArcaClass.ACOES] == pytest.approx(10_000.0)


def test_stock_sales_up_to_twenty_thousand_are_exempt() -> None:
    small = run_backtest(_two_classes(AssetType.STOCK_BR), HISTORY, HALF, _config(10_000.0))
    large = run_backtest(_two_classes(AssetType.STOCK_BR), HISTORY, HALF, _config(100_000.0))

    # Small: 12 whole shares sold for 2.400 (exempt). Large: 125 shares for 25.000 > 20.000,
    # 15% on a gain of 12.500.
    assert small.summary.sales == 1 and small.summary.taxes == 0.0
    assert large.summary.taxes == pytest.approx(1875.0)


def test_policy_in_force_on_each_date() -> None:
    v1 = _policy(datetime(2025, 1, 1, tzinfo=UTC), ACOES=100.0)
    v2 = _policy(datetime(2025, 3, 1, tzinfo=UTC), CAIXA=100.0)
    assert policy_on(date(2024, 12, 31), v2, [v2, v1]) is v1  # before any version: the first
    assert policy_on(date(2025, 2, 28), v2, [v1, v2]) is v1
    assert policy_on(date(2025, 3, 31), v1, [v1, v2]) is v2
    assert policy_on(date(2025, 3, 31), v1, []) is v1

    config = BacktestConfig(START, END, 1000.0, fee_rate=0.0, cash_symbol=None)
    flat = MarketHistory({"A": _series(100.0, 100.0, 100.0), "C": _series(100.0, 100.0, 100.0)})
    result = run_backtest(
        _two_classes(AssetType.STOCK_INTL), flat, v1, config, policy_versions=[v1, v2]
    )

    assert result.points[1].by_class.get(ArcaClass.CAIXA, 0.0) == 0.0
    assert result.points[2].by_class[ArcaClass.CAIXA] == pytest.approx(1000.0)


def _answer(qid: str, value: AnswerValue | None, when: datetime) -> ChecklistAnswer:
    return ChecklistAnswer(qid, value, AnswerSource.MANUAL, None, when)


def test_answers_on_follow_the_history_and_clears() -> None:
    asset = SimulatedAsset(
        "B",
        "B",
        AssetType.STOCK_INTL,
        ArcaClass.ACOES,
        answers=(
            _answer("governance", AnswerValue.YES, datetime(2025, 2, 10, tzinfo=UTC)),
            _answer("governance", None, datetime(2025, 3, 10, tzinfo=UTC)),
            _answer("age_30y", AnswerValue.NO, datetime(2025, 1, 5, tzinfo=UTC)),
        ),
    )
    assert set(answers_on(asset, date(2025, 1, 31))) == {"age_30y"}
    assert answers_on(asset, date(2025, 2, 28))["governance"].value == AnswerValue.YES
    assert "governance" not in answers_on(asset, date(2025, 3, 31))


def test_checklist_answers_change_the_split_from_their_date() -> None:
    answered = datetime(2025, 2, 10, tzinfo=UTC)
    assets = [
        SimulatedAsset(
            "A",
            "A",
            AssetType.STOCK_INTL,
            ArcaClass.ACOES,
            checklist_profile=ChecklistProfile.STOCK,
        ),
        SimulatedAsset(
            "B",
            "B",
            AssetType.STOCK_INTL,
            ArcaClass.ACOES,
            checklist_profile=ChecklistProfile.STOCK,
            answers=(
                _answer("governance", AnswerValue.YES, answered),
                _answer("age_30y", AnswerValue.YES, answered),
            ),
        ),
    ]
    flat = MarketHistory({"A": _series(10.0, 10.0, 10.0), "B": _series(10.0, 10.0, 10.0)})
    config = BacktestConfig(START, END, 1000.0, fee_rate=0.0, cash_symbol=None)

    result = run_backtest(assets, flat, _policy(ACOES=100.0), config)

    # January: no answers yet, both assets get half. From February B has the only positive
    # score, so it alone receives the money (six purchases without the answers).
    assert result.points[1].market_value == pytest.approx(2000.0)
    assert result.summary.trades == 2 + 1 + 1


def test_catalog_assets_flag_survivorship_bias() -> None:
    config = BacktestConfig(START, END, 1000.0, fee_rate=0.0, cash_symbol=None)
    flat = MarketHistory({"A": _series(10.0, 10.0, 10.0)})
    held = [SimulatedAsset("A", "A", AssetType.STOCK_INTL, ArcaClass.ACOES)]
    catalog = [SimulatedAsset("A", "A", AssetType.STOCK_INTL, ArcaClass.ACOES, from_catalog=True)]
    policy = _policy(ACOES=100.0)

    assert run_backtest(held, flat, policy, config).survivorship_bias is False
    assert run_backtest(catalog, flat, policy, config).survivorship_bias is True
