"""Phase 48.R9: saved views of the screens and the monthly report."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from core.errors import ValidationError
from domain.planning.goals import Goal, GoalKind, GoalProgress, GoalStatus
from domain.portfolio.services.monthly_report import build_report, month_end
from domain.shared.entities import (
    AssetEntity,
    EarningEntity,
    PortfolioSnapshotEntity,
    TransactionEntity,
)
from domain.shared.enums import AssetType, EarningKind, TransactionKind
from domain.views.services import MAX_VIEWS_PER_SCOPE, clean_name

D = Decimal
NOV = date(2026, 10, 1)


# --- saved views ------------------------------------------------------------------------------


def test_clean_name_squeezes_spaces_and_refuses_bad_input() -> None:
    assert clean_name("  Dividendos   altos ", {}) == "Dividendos altos"
    with pytest.raises(ValidationError) as empty:
        clean_name("   ", {})
    assert empty.value.code == "EMPTY_VIEW_NAME"
    with pytest.raises(ValidationError) as big:
        clean_name("x", {"q": "a" * 5000})
    assert big.value.code == "VIEW_FILTERS_TOO_LARGE"


def test_saved_views_crud_per_screen(api: SimpleNamespace) -> None:
    body = {"scope": "SCREENER", "name": "FIIs baratos", "filters": {"pvp_max": 0.9}}
    first = api.client.put("/api/v1/saved-views", json=body)
    assert first.status_code == 200, first.text
    view = first.json()
    assert view["filters"] == {"pvp_max": 0.9}

    # the same name in the same screen replaces the filters
    again = api.client.put(
        "/api/v1/saved-views", json={**body, "name": " FIIs  baratos", "filters": {"pvp_max": 1}}
    ).json()
    assert again["id"] == view["id"] and again["filters"] == {"pvp_max": 1}
    # the same name in another screen is another view
    api.client.put("/api/v1/saved-views", json={**body, "scope": "LEDGER"})

    listed = api.client.get("/api/v1/saved-views?scope=SCREENER").json()
    assert [v["name"] for v in listed] == ["FIIs baratos"]
    assert len(api.client.get("/api/v1/saved-views?scope=LEDGER").json()) == 1
    assert api.client.get("/api/v1/saved-views?scope=NOPE").status_code == 422

    assert api.client.delete(f"/api/v1/saved-views/{view['id']}").status_code == 204
    assert api.client.delete(f"/api/v1/saved-views/{view['id']}").status_code == 404


def test_saved_views_are_limited_per_screen(api: SimpleNamespace) -> None:
    for i in range(MAX_VIEWS_PER_SCOPE):
        api.client.put("/api/v1/saved-views", json={"scope": "PORTFOLIO", "name": f"v{i}"})
    extra = api.client.put("/api/v1/saved-views", json={"scope": "PORTFOLIO", "name": "extra"})
    assert extra.status_code == 400 and extra.json()["code"] == "TOO_MANY_VIEWS"
    # replacing an existing one still works at the limit
    assert (
        api.client.put("/api/v1/saved-views", json={"scope": "PORTFOLIO", "name": "v0"}).status_code
        == 200
    )


# --- monthly report (pure) --------------------------------------------------------------------


def _snap(day: date, value: float, flow: float = 0.0, earnings: float = 0.0, **kw):
    return PortfolioSnapshotEntity(
        snapshot_date=day,
        invested_value=value,
        market_value=value,
        unrealized_pnl=0.0,
        net_flow=flow,
        earnings_cum=earnings,
        **kw,
    )


def _asset() -> AssetEntity:
    return AssetEntity(
        id=1,
        ticker="HGLG11",
        name="CSHG Log",
        asset_type=AssetType.FII,
        transactions=(
            TransactionEntity(1, TransactionKind.BUY, date(2026, 9, 30), D("10"), D("100")),
            TransactionEntity(
                1, TransactionKind.BUY, date(2026, 10, 10), D("10"), D("100"), fees=D("1")
            ),
            TransactionEntity(
                1, TransactionKind.SELL, date(2026, 10, 20), D("2"), D("110"), fees=D("0.5")
            ),
        ),
        earnings=(
            EarningEntity(1, EarningKind.DIVIDEND, date(2026, 10, 14), D("11")),
            EarningEntity(1, EarningKind.DIVIDEND, date(2026, 11, 14), D("12")),
        ),
    )


def test_report_measures_the_month_with_flows_and_income() -> None:
    opening = _snap(date(2026, 9, 30), 1000)
    in_month = [
        _snap(date(2026, 10, 10), 2050, flow=1001),
        _snap(
            date(2026, 10, 31),
            1900,
            flow=-219.5,
            earnings=11,
            by_class={
                "REAL_ESTATE": {"current_value": 1900, "current_pct": 1.0, "target_pct": 0.3}
            },
        ),
    ]
    goal = Goal(GoalKind.WEALTH, "Meta", D("10000"), date(2030, 1, 1), D("100"), D("0.06"))
    progress = GoalProgress(goal, 38, 1900, 10000, 1900, 0.19, 9000, 150, GoalStatus.OFF_TRACK)

    r = build_report(NOV, opening=opening, in_month=in_month, assets=[_asset()], goals=[progress])

    assert (r.start_date, r.end_date) == (date(2026, 9, 30), date(2026, 10, 31))
    assert (r.start_value_brl, r.end_value_brl) == (1000, 1900)
    assert (r.bought_brl, r.sold_brl) == (1001, 219.5)
    assert r.net_flow_brl == 781.5
    assert r.income_brl == 11  # the November payment is not in October
    assert r.result_brl == round(1900 - 1000 - 781.5 + 11, 2)
    assert r.month_return is not None and r.month_return > 0
    assert [t.kind for t in r.trades] == ["BUY", "SELL"]
    assert r.allocation[0].arca_class == "REAL_ESTATE" and r.allocation[0].target_pct == 0.3
    assert [g.name for g in r.goals] == ["Meta"]
    assert r.data_gaps == []


def test_report_without_snapshots_says_what_is_missing() -> None:
    r = build_report(NOV, opening=None, in_month=[], assets=[])
    assert r.month_return is None and r.result_brl == 0
    assert len(r.data_gaps) == 2
    assert month_end(date(2028, 2, 1)) == date(2028, 2, 29)


# --- monthly report (API) ---------------------------------------------------------------------


def test_monthly_report_route(api: SimpleNamespace) -> None:
    with api.uow_factory() as uow:
        uow.snapshots.upsert(_snap(date(2026, 9, 30), 1000))
        uow.snapshots.upsert(_snap(date(2026, 10, 30), 1100))
        uow.commit()
    body = api.client.get("/api/v1/portfolio/monthly-report?month=2026-10").json()
    assert body["start_value_brl"] == 1000 and body["end_value_brl"] == 1100
    assert body["month_return"] == pytest.approx(0.1)
    assert body["tax"] is None and body["trades"] == []

    bad = api.client.get("/api/v1/portfolio/monthly-report?month=2026-13")
    assert bad.status_code == 400 and bad.json()["code"] == "INVALID_MONTH"
    future = api.client.get("/api/v1/portfolio/monthly-report?month=2999-01")
    assert future.json()["code"] == "INVALID_MONTH"
