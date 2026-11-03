"""Phase 34: the optimizer's verdict per class, the portfolio's limit per asset and the transition.

The income tax of the sales was worked out by hand in each test, from the rule: 15% on the
month's gain of stocks, only above R$ 20 thousand of stock sales; 20% on FII gains."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from domain.policy.services.policy import ArcaPolicy, ClassPolicy, InvestmentPolicy
from domain.recommendation.construction import set_weights
from domain.recommendation.optimizer import optimizer_applies
from domain.recommendation.params import ConstructionParams
from domain.recommendation.runs import class_params
from domain.recommendation.transition import (
    TOLERANCE,
    TransitionHolding,
    added_tax,
    contribution_path,
    distance_to,
    plan_transition,
    split_sales,
)
from domain.shared.enums import ArcaClass, AssetType
from domain.tax.assessment import Sale
from domain.tax.services.rules import DEFAULT_RULE_BOOK

TODAY = date(2026, 11, 3)


def _holding(ticker: str, qty: float, value: float, invested: float, kind=AssetType.STOCK_BR):
    return TransitionHolding(1, ticker, kind, qty, value, invested)


def _plan(holdings, targets, *, expected=None, monthly=0.0, past=()):
    return plan_transition(
        holdings=holdings,
        targets=targets,
        expected=expected or {},
        monthly_brl=monthly,
        past_sales=list(past),
        book=DEFAULT_RULE_BOOK,
        today=TODAY,
    )


# --- verdict per class ------------------------------------------------------------------------


def test_the_optimizer_only_applies_to_the_class_its_test_covers() -> None:
    assert optimizer_applies("ACOES", True)
    assert not optimizer_applies("ACOES", False)
    assert not optimizer_applies("REAL_ESTATE", True)
    assert not optimizer_applies("ATIVOS_INTERNACIONAIS", True)


# --- contributions only -----------------------------------------------------------------------


def test_distance_is_the_share_out_of_place() -> None:
    assert distance_to({"A": 50, "B": 50}, {"A": 0.5, "B": 0.5}) == 0
    assert distance_to({"A": 100}, {"B": 1.0}) == 1
    assert distance_to({}, {"A": 1.0}) == 1


def test_contributions_reach_the_target_and_say_how_long() -> None:
    # 100/0 towards 50/50: at 60 a month, after n months B holds 60n of 100 + 60n; it is within
    # 5% of the target (45%) once 60n >= 0.45(100 + 60n), that is, n >= 1.36: two months.
    months, first = contribution_path({"A": 100.0}, {"A": 0.5, "B": 0.5}, 60.0)
    assert months == 2
    assert first == {"B": 60.0}


def test_contributions_already_there_or_with_no_money() -> None:
    assert contribution_path({"A": 50.0, "B": 50.0}, {"A": 0.5, "B": 0.5}, 0.0) == (0, {})
    assert contribution_path({"A": 100.0}, {"B": 1.0}, 0.0) == (None, {})


# --- with sales: the tax by hand ---------------------------------------------------------------


def test_stock_sales_within_the_exemption_pay_no_tax() -> None:
    # Sells 50 of 100 at R$ 100 = R$ 5,000, below R$ 20 thousand.
    plan = _plan(
        [_holding("A", 100, 10_000, 5_000)],
        {"A": 0.5, "B": 0.5},
    )
    assert [(s.ticker, s.quantity, s.value_brl, s.cost_brl) for s in plan.sales] == [
        ("A", 50.0, 5_000.0, 2_500.0)
    ]
    assert plan.tax_brl == 0
    assert plan.split_months is None


def test_stock_sales_above_the_exemption_pay_15_percent_and_can_be_split() -> None:
    # Sells 500 of 1,000 at R$ 100 = R$ 50,000; cost R$ 25,000; fee 0.03% = R$ 15.
    # Gain R$ 24,985; tax 15% = R$ 3,747.75. In 3 months each sale is R$ 16,666.67: exempt.
    plan = _plan(
        [_holding("A", 1000, 100_000, 50_000)],
        {"A": 0.5, "B": 0.5},
    )
    assert plan.sold_brl == 50_000
    assert plan.tax_brl == pytest.approx(3_747.75, abs=0.01)
    assert plan.split_months == 3
    assert plan.split_tax_brl == 0


def test_fii_sales_pay_20_percent_with_no_exemption() -> None:
    # Sells 50 of 100 at R$ 100 = R$ 5,000; cost R$ 4,000; fee R$ 1.50: gain R$ 998.50, tax 20%.
    plan = _plan(
        [_holding("HGLG11", 100, 10_000, 8_000, AssetType.FII)],
        {"HGLG11": 0.5, "XPLG11": 0.5},
    )
    assert plan.tax_brl == pytest.approx(199.70, abs=0.01)
    assert plan.split_months is None


def test_a_loss_already_carried_reduces_the_tax() -> None:
    # A past FII sale lost R$ 500 (fee 0): the R$ 998.50 gain above pays on R$ 498.50.
    past = Sale(
        9,
        "OLD11",
        AssetType.FII,
        date(2026, 1, 10),
        Decimal("10"),
        Decimal("500"),
        Decimal("1000"),
        Decimal("0"),
        False,
    )
    plan = _plan(
        [_holding("HGLG11", 100, 10_000, 8_000, AssetType.FII)],
        {"HGLG11": 0.5, "XPLG11": 0.5},
        past=[past],
    )
    assert plan.tax_brl == pytest.approx(99.70, abs=0.01)


def test_sales_already_made_in_the_month_count_for_the_exemption() -> None:
    # R$ 18,000 of stock sold this month with no gain, plus R$ 5,000 now: above the exemption,
    # so the R$ 2,498.50 gain of the new sale pays 15%.
    past = Sale(
        9,
        "OLD3",
        AssetType.STOCK_BR,
        date(2026, 11, 1),
        Decimal("10"),
        Decimal("18000"),
        Decimal("18000"),
        Decimal("0"),
        False,
    )
    plan = _plan([_holding("A", 100, 10_000, 5_000)], {"A": 0.5, "B": 0.5}, past=[past])
    assert plan.tax_brl == pytest.approx(374.78, abs=0.01)


def test_whole_units_of_a_stock_and_a_loss_pays_nothing() -> None:
    plan = _plan([_holding("A", 3, 300, 600)], {"A": 0.5, "B": 0.5})
    assert plan.sales[0].quantity == 1  # half of 3 is 1.5: only whole shares
    assert plan.sales[0].gain_brl < 0 and plan.tax_brl == 0


def test_added_tax_is_never_negative() -> None:
    gain = Sale(
        1,
        "A",
        AssetType.FII,
        TODAY,
        Decimal("1"),
        Decimal("200"),
        Decimal("100"),
        Decimal("0"),
        False,
    )
    loss = Sale(
        2,
        "B",
        AssetType.FII,
        TODAY,
        Decimal("1"),
        Decimal("100"),
        Decimal("200"),
        Decimal("0"),
        False,
    )
    assert added_tax([gain], [loss], DEFAULT_RULE_BOOK, TODAY) == 0


def test_split_only_divides_the_stock_sales() -> None:
    stock = Sale(
        1,
        "A",
        AssetType.STOCK_BR,
        date(2026, 12, 31),
        Decimal("9"),
        Decimal("900"),
        Decimal("300"),
        Decimal("3"),
        False,
    )
    fii = Sale(
        2,
        "B",
        AssetType.FII,
        date(2026, 12, 31),
        Decimal("1"),
        Decimal("100"),
        Decimal("50"),
        Decimal("0"),
        False,
    )
    parts = split_sales([stock, fii], 3)
    assert [p.on for p in parts if p.ticker == "A"] == [
        date(2026, 12, 31),
        date(2027, 1, 31),
        date(2027, 2, 28),
    ]
    assert sum(p.sale_value_brl for p in parts if p.ticker == "A") == Decimal("900")
    assert [p.on for p in parts if p.ticker == "B"] == [date(2026, 12, 31)]


# --- does it pay? ------------------------------------------------------------------------------


def test_payback_compares_the_cost_with_the_expected_gain() -> None:
    # R$ 49,xxx moves from an asset expected at 0% to one at 10%: about R$ 4,800 a year against
    # a cost of about R$ 3,777: under 36 months, it pays off.
    plan = _plan(
        [_holding("A", 1000, 100_000, 50_000)],
        {"A": 0.5, "B": 0.5},
        expected={"B": 0.10},
    )
    assert plan.expected_gain_year_brl == pytest.approx(4_623, abs=5)
    assert plan.cost_brl == pytest.approx(3_777, abs=2)
    assert plan.payback_months == pytest.approx(9.8, abs=0.2)
    assert plan.pays_off

    no_gain = _plan([_holding("A", 1000, 100_000, 50_000)], {"A": 0.5, "B": 0.5})
    assert no_gain.payback_months is None and not no_gain.pays_off


def test_a_class_on_target_needs_nothing() -> None:
    plan = _plan(
        [_holding("A", 100, 5_000, 4_000), _holding("B", 100, 5_000, 4_000)],
        {"A": 0.5, "B": 0.5},
        monthly=100.0,
    )
    assert plan.months == 0 and plan.sales == [] and plan.cost_brl == 0
    assert plan.distance <= TOLERANCE


def test_an_empty_class_only_has_the_contribution_path() -> None:
    plan = _plan([], {"A": 1.0}, monthly=100.0)
    assert plan.total_brl == 0 and plan.sales == [] and plan.months == 1


# --- API --------------------------------------------------------------------------------------


def test_transition_route_without_a_run(api: SimpleNamespace) -> None:
    body = api.client.get(
        "/api/v1/recommendation/transition?arca_class=ACOES&monthly_brl=500"
    ).json()
    assert body["status"] == "NOT_COMPUTED" and body["arca_class"] == "ACOES"
    assert api.client.get("/api/v1/recommendation/transition?arca_class=NOPE").status_code == 422
    assert (
        api.client.get(
            "/api/v1/recommendation/transition?arca_class=ACOES&monthly_brl=-1"
        ).status_code
        == 422
    )


# --- the portfolio's limit per asset ------------------------------------------------------------


def _policy(target: float) -> InvestmentPolicy:
    rest = (100.0 - target) / 3.0
    classes = {c: ClassPolicy(target_pct=rest) for c in ArcaClass}
    classes[ArcaClass.ACOES] = ClassPolicy(target_pct=target)
    return InvestmentPolicy(arca=ArcaPolicy(classes))


def test_the_limit_of_the_portfolio_is_seen_from_the_class() -> None:
    # The Saúde warns at 15% of the portfolio: 21.4% of a class that is 70% of it.
    assert class_params(_policy(70.0), ArcaClass.ACOES).asset_cap == pytest.approx(0.15 / 0.70)
    assert class_params(_policy(25.0), ArcaClass.ACOES).asset_cap == pytest.approx(0.60)
    assert class_params(_policy(10.0), ArcaClass.ACOES).asset_cap == 1.0
    assert ConstructionParams().asset_cap == 1.0


def _rows(*scores: float) -> list[SimpleNamespace]:
    return [SimpleNamespace(ticker=f"T{i}", score=s) for i, s in enumerate(scores)]


def test_the_construction_respects_the_limit_per_asset() -> None:
    rows = _rows(9, 1, 1, 1, 1, 1, 1)
    labels = {r.ticker: r.ticker for r in rows}
    free = ConstructionParams(sector_cap=1.0, group_cap=1.0)
    weights, _ = set_weights(rows, labels, labels, free)
    assert weights["T0"] == pytest.approx(0.6)

    capped = ConstructionParams(sector_cap=1.0, group_cap=1.0, asset_cap=0.2)
    weights, notes = set_weights(rows, labels, labels, capped)
    assert max(weights.values()) == pytest.approx(0.2)
    assert sum(weights.values()) == pytest.approx(1.0)
    assert notes == []


def test_too_few_assets_raise_the_limit_and_say_so() -> None:
    rows = _rows(1, 1, 1)
    labels = {r.ticker: r.ticker for r in rows}
    params = ConstructionParams(sector_cap=1.0, group_cap=1.0, asset_cap=0.2)
    weights, notes = set_weights(rows, labels, labels, params)
    assert max(weights.values()) == pytest.approx(1 / 3)
    assert any("Poucos ativos" in n for n in notes)
