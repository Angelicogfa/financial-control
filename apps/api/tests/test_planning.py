"""Planejar (Phase 48.R8): goals with progress and required contribution, and future income."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from domain.planning.goals import (
    Goal,
    GoalKind,
    GoalStatus,
    future_value,
    monthly_rate,
    months_between,
    progress_of,
    required_contribution,
    target_wealth,
)
from domain.planning.income_forecast import DeclaredIncome, forecast_income
from domain.shared.entities import AssetEntity, EarningEntity, TransactionEntity
from domain.shared.enums import AssetType, EarningKind, TransactionKind

TODAY = date(2026, 11, 2)
D = Decimal


def _goal(**kw) -> Goal:
    base = {
        "kind": GoalKind.WEALTH,
        "name": "Independência",
        "target_brl": D("1000000"),
        "target_date": date(2036, 11, 2),
        "monthly_contribution_brl": D("3000"),
        "annual_return": D("0.06"),
    }
    base.update(kw)
    return Goal(**base)


# --- goals (pure) -----------------------------------------------------------------------------


def test_months_and_rates() -> None:
    assert months_between(date(2026, 11, 2), date(2036, 11, 2)) == 120
    assert months_between(date(2026, 11, 15), date(2026, 12, 14)) == 0
    assert months_between(date(2026, 11, 2), date(2025, 1, 1)) == 0
    assert monthly_rate(D("0.12")) == pytest.approx(0.009489, abs=1e-6)


def test_future_value_and_required_contribution_are_inverse() -> None:
    rate = monthly_rate(D("0.06"))
    fv = future_value(100000, 2000, rate, 120)
    assert required_contribution(100000, fv, rate, 120) == pytest.approx(2000, abs=0.01)
    assert future_value(1000, 100, 0.0, 10) == 2000
    assert required_contribution(1000, 2000, 0.0, 10) == 100
    assert required_contribution(5000, 2000, rate, 10) == 0  # already there with growth alone
    assert required_contribution(1000, 2000, rate, 0) == 1000


def test_wealth_goal_on_and_off_track() -> None:
    on = progress_of(_goal(), wealth=400000, monthly_income=0, today=TODAY)
    assert on.status == GoalStatus.ON_TRACK and on.months_left == 120
    assert on.progress == 0.4
    assert on.projected_wealth_brl == pytest.approx(
        future_value(400000, 3000, monthly_rate(D("0.06")), 120), abs=0.01
    )

    off = progress_of(
        _goal(monthly_contribution_brl=D("0")), wealth=100000, monthly_income=0, today=TODAY
    )
    assert off.status == GoalStatus.OFF_TRACK
    assert off.required_monthly_brl == pytest.approx(
        required_contribution(100000, 1000000, monthly_rate(D("0.06")), 120), abs=0.01
    )

    assert (
        progress_of(_goal(), wealth=1200000, monthly_income=0, today=TODAY).status
        == GoalStatus.REACHED
    )
    missed = progress_of(
        _goal(target_date=TODAY - timedelta(days=1)), wealth=100, monthly_income=0, today=TODAY
    )
    assert missed.status == GoalStatus.MISSED


def test_passive_income_goal_needs_the_wealth_that_pays_it() -> None:
    goal = _goal(kind=GoalKind.PASSIVE_INCOME, target_brl=D("5000"), income_yield=D("0.06"))
    assert target_wealth(goal) == 1000000  # 5,000 x 12 / 6%
    p = progress_of(goal, wealth=300000, monthly_income=1500, today=TODAY)
    assert (p.current_brl, p.progress, p.target_wealth_brl) == (1500, 0.3, 1000000)


# --- future income (pure) ---------------------------------------------------------------------


def _fii(
    earnings: list[tuple[date, str]], qty_then: str = "100", qty_now: str = "150"
) -> AssetEntity:
    trades = [
        TransactionEntity(
            asset_id=1,
            kind=TransactionKind.BUY,
            trade_date=date(2025, 1, 2),
            quantity=D(qty_then),
            unit_price=D("100"),
        ),
    ]
    extra = D(qty_now) - D(qty_then)
    if extra > 0:
        trades.append(
            TransactionEntity(
                asset_id=1,
                kind=TransactionKind.BUY,
                trade_date=date(2026, 10, 20),
                quantity=extra,
                unit_price=D("100"),
            )
        )
    return AssetEntity(
        id=1,
        ticker="HGLG11",
        name="HGLG11",
        asset_type=AssetType.FII,
        transactions=tuple(trades),
        earnings=tuple(
            EarningEntity(
                asset_id=1,
                kind=EarningKind.FII_YIELD,
                payment_date=on,
                gross_amount=D(v),
                net_amount=D(v),
            )
            for on, v in earnings
        ),
    )


def test_estimate_repeats_each_month_of_last_year_at_todays_quantity() -> None:
    fii = _fii([(date(2025, 11, 14), "110"), (date(2026, 3, 14), "120")])
    f = forecast_income([fii], [], today=TODAY, months=12)
    months = {m.month: m for m in f.months}
    assert months["2026-11"].estimated_brl == pytest.approx(165.0)  # 1.10 per unit x 150 units
    assert months["2027-03"].estimated_brl == pytest.approx(180.0)
    assert months["2026-12"].total_brl == 0
    assert f.next_12m_brl == pytest.approx(345.0)
    assert [(a.ticker, a.next_12m_brl) for a in f.assets] == [("HGLG11", 345.0)]


def test_declared_income_replaces_the_estimate_of_that_month() -> None:
    fii = _fii([(date(2025, 11, 14), "110")])
    declared = [
        DeclaredIncome(asset_id=1, ticker="HGLG11", payment_date=date(2026, 11, 14), net_brl=172.5)
    ]
    f = forecast_income([fii], declared, today=TODAY, months=12)
    november = next(m for m in f.months if m.month == "2026-11")
    assert (november.declared_brl, november.estimated_brl) == (172.5, 0)
    assert f.declared_brl == 172.5


def test_a_longer_horizon_repeats_the_year_and_sold_assets_pay_nothing() -> None:
    fii = _fii([(date(2025, 11, 14), "110")])
    f = forecast_income([fii], [], today=TODAY, months=24)
    assert len(f.months) == 24
    assert sum(1 for m in f.months if m.estimated_brl > 0) == 2
    sold = _fii([(date(2025, 11, 14), "110")], qty_now="100")
    sold = AssetEntity(
        **{
            **sold.__dict__,
            "transactions": (
                *sold.transactions,
                TransactionEntity(
                    asset_id=1,
                    kind=TransactionKind.SELL,
                    trade_date=date(2026, 10, 1),
                    quantity=D("100"),
                    unit_price=D("100"),
                ),
            ),
        }
    )
    assert forecast_income([sold], [], today=TODAY).next_12m_brl == 0


# --- API --------------------------------------------------------------------------------------


def test_goals_crud_with_progress(api: SimpleNamespace) -> None:
    created = api.client.post(
        "/api/v1/goals",
        json={
            "kind": "PASSIVE_INCOME",
            "name": "Renda de R$ 5 mil",
            "target_brl": "5000",
            "target_date": (date.today() + timedelta(days=3650)).isoformat(),
            "monthly_contribution_brl": "2000",
        },
    )
    assert created.status_code == 201, created.text
    goal = created.json()
    assert goal["target_wealth_brl"] == 1000000.0
    assert goal["status"] == "OFF_TRACK" and goal["required_monthly_brl"] > 2000
    assert goal["current_wealth_brl"] == 0

    updated = api.client.put(
        f"/api/v1/goals/{goal['id']}", json={"monthly_contribution_brl": "8000"}
    ).json()
    assert updated["status"] == "ON_TRACK"
    assert [g["id"] for g in api.client.get("/api/v1/goals").json()] == [goal["id"]]
    assert api.client.delete(f"/api/v1/goals/{goal['id']}").status_code == 204
    assert api.client.delete(f"/api/v1/goals/{goal['id']}").status_code == 404


def test_goals_validate(api: SimpleNamespace) -> None:
    future = (date.today() + timedelta(days=400)).isoformat()
    past = api.client.post(
        "/api/v1/goals",
        json={
            "kind": "WEALTH",
            "name": "x",
            "target_brl": "1000",
            "target_date": date.today().isoformat(),
        },
    )
    assert past.status_code == 400 and past.json()["code"] == "INVALID_TARGET_DATE"
    blank = api.client.post(
        "/api/v1/goals",
        json={"kind": "WEALTH", "name": "  ", "target_brl": "1000", "target_date": future},
    )
    assert blank.json()["code"] == "EMPTY_GOAL_NAME"
    wild = api.client.post(
        "/api/v1/goals",
        json={
            "kind": "WEALTH",
            "name": "x",
            "target_brl": "1000",
            "target_date": future,
            "annual_return": "2",
        },
    )
    assert wild.json()["code"] == "INVALID_RETURN"
    assert (
        api.client.post(
            "/api/v1/goals",
            json={"kind": "WEALTH", "name": "x", "target_brl": "0", "target_date": future},
        ).status_code
        == 422
    )


def test_income_forecast_route(api: SimpleNamespace) -> None:
    body = api.client.get("/api/v1/portfolio/income-forecast?months=24").json()
    assert len(body["months"]) == 24 and body["next_12m_brl"] == 0
    assert (
        api.client.get("/api/v1/portfolio/income-forecast?months=7").json()["code"]
        == "INVALID_MONTHS"
    )
