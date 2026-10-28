"""Phase 32.4: implausible health numbers traced to bad prints and to large same-day flows.

Real cases (28/10/2026): Yahoo had XPML11 at R$ 1.07 from 14 to 16/01/2026 between closes
near R$ 110 (portfolio volatility of 591% a year, 100% of the risk on 0.8% of the weight);
on 21/10/2025 a R$ 2,729.98 purchase on a R$ 32.12 portfolio closed at R$ 2,628.61, a -416%
day for the end-of-period TWR (rolling 12-month return of -394%).
"""

from __future__ import annotations

import random
from datetime import date, timedelta

import pytest

from domain.market.entities import PricePoint
from domain.market.services.price_sanity import price_spikes
from domain.policy.services.policy import HealthPolicy
from domain.portfolio.services.analytics import dated_time_weighted_returns
from domain.portfolio.services.health import (
    ASSET_SERIES_CHECKS,
    PORTFOLIO_SERIES_CHECKS,
    HealthInputs,
    Holding,
    diagnose,
)
from domain.portfolio.services.health_inputs import clean_histories, drop_impossible_periods
from domain.portfolio.services.risk_metrics import class_time_weighted_returns
from domain.shared.entities import PortfolioSnapshotEntity
from domain.shared.enums import ArcaClass, AssetType
from domain.simulation.data import _price_series

D0 = date(2026, 1, 12)


def _days(n: int) -> list[date]:
    return [D0 + timedelta(days=i) for i in range(n)]


# --- bad prints ----------------------------------------------------------------------------------


def test_a_short_run_out_of_scale_that_comes_back_is_dropped() -> None:
    prices = [110.1, 110.13, 1.068, 1.061, 1.064, 109.58, 109.9]
    keep, spikes = price_spikes(_days(7), prices)
    assert keep == [True, True, False, False, False, True, True]
    assert len(spikes) == 1 and spikes[0].points == 3
    assert spikes[0].first_date == D0 + timedelta(days=2)
    assert spikes[0].last_date == D0 + timedelta(days=4)
    assert "1.07 contra 110.13" in spikes[0].describe()


def test_real_moves_and_level_changes_are_kept() -> None:
    # A crash that does not come back, an unapplied split and a large but plausible day.
    for prices in (
        [100.0, 98.0, 20.0, 19.0, 18.5, 18.0, 17.0, 16.0],
        [40.0, 41.0, 10.2, 10.3, 10.1, 10.4, 10.2],
    ):
        keep, spikes = price_spikes(_days(len(prices)), prices)
        assert all(keep) and spikes == []
    keep, _ = price_spikes(_days(4), [100.0, 150.0, 140.0, 145.0])
    assert all(keep)
    # The last points cannot be judged: there is nothing after them.
    keep, spikes = price_spikes(_days(3), [100.0, 101.0, 1.0])
    assert all(keep) and spikes == []


def test_clean_histories_reports_what_was_dropped() -> None:
    prices = [110.0, 110.1, 1.07, 109.6, 109.8]
    points = [PricePoint(date=d, close=p) for d, p in zip(_days(5), prices, strict=True)]
    cleaned, notes = clean_histories({"XPML11": points, "WEGE3": points[:2]})
    assert [p.close for p in cleaned["XPML11"]] == [110.0, 110.1, 109.6, 109.8]
    assert len(cleaned["WEGE3"]) == 2
    assert len(notes) == 1 and notes[0].startswith("XPML11: preço do provedor fora de escala")


def test_the_simulation_history_drops_bad_prints_too() -> None:
    series = _price_series(
        [(d, p) for d, p in zip(_days(5), [50.0, 51.0, 0.5, 51.5, 52.0], strict=True)]
    )
    assert series.prices == (50.0, 51.0, 51.5, 52.0)


# --- flows larger than the portfolio ------------------------------------------------------------


def _snap(day: date, value: float, flow: float = 0.0, **kw: object) -> PortfolioSnapshotEntity:
    return PortfolioSnapshotEntity(
        snapshot_date=day,
        invested_value=0.0,
        market_value=value,
        unrealized_pnl=0.0,
        net_flow=flow,
        **kw,  # type: ignore[arg-type]
    )


def test_a_purchase_counts_from_the_start_of_the_day() -> None:
    snaps = [_snap(date(2025, 10, 20), 32.12), _snap(date(2025, 10, 21), 2628.61, 2729.98)]
    _, end_of_period = dated_time_weighted_returns(snaps)
    assert end_of_period[0] == pytest.approx(-4.156, abs=1e-3)  # the bug: -416% in one day
    _, at_start = dated_time_weighted_returns(snaps, purchases_at_start=True)
    assert at_start[0] == pytest.approx((2628.61 - 32.12 - 2729.98) / (32.12 + 2729.98))
    assert at_start[0] == pytest.approx(-0.0484, abs=1e-4)
    # Sales still leave at the end: the base is the value before them.
    sale = [_snap(date(2025, 3, 6), 373.83), _snap(date(2025, 3, 7), 36.08, -395.85)]
    _, rs = dated_time_weighted_returns(sale, purchases_at_start=True)
    assert rs[0] == pytest.approx((36.08 - 373.83 + 395.85) / 373.83)


def test_class_returns_use_the_same_convention() -> None:
    before = {"ACOES": {"current_value": 30.0, "invested_value": 30.0}}
    after = {"ACOES": {"current_value": 2600.0, "invested_value": 2730.0}}
    snaps = [
        _snap(date(2025, 10, 20), 30.0, by_class=before),
        _snap(date(2025, 10, 21), 2600.0, by_class=after),
    ]
    result = class_time_weighted_returns(snaps)["ACOES"]
    assert result == pytest.approx((2600.0 - 30.0 - 2700.0) / 2730.0, abs=1e-4)
    assert result > -1.0


def test_impossible_periods_are_dropped_with_a_note() -> None:
    dates = [date(2025, 10, 20), date(2025, 10, 21), date(2025, 10, 22)]
    kept_dates, kept, notes = drop_impossible_periods(dates, [0.01, -4.156, 0.002])
    assert kept == [0.01, 0.002] and kept_dates == [dates[0], dates[2]]
    assert notes == ["21/10/2025 (-415.6%)"]


# --- the health report marks what it computed without --------------------------------------------


def test_diagnose_marks_the_checks_built_from_cleaned_series() -> None:
    rng = random.Random(1)
    n = 260
    dates = [date(2025, 1, 1) + timedelta(days=i) for i in range(n)]
    returns = [0.0004 + rng.gauss(0.0, 0.01) for _ in range(n)]
    holdings = [
        Holding(
            ticker=t,
            name=t,
            asset_type=AssetType.STOCK_BR,
            arca_class=ArcaClass.ACOES,
            value_brl=5000.0,
            sector=s,
        )
        for t, s in (("WEGE3", "Industrials"), ("ITUB4", "Financial Services"))
    ]
    report = diagnose(
        HealthInputs(
            as_of=dates[-1],
            holdings=holdings,
            asset_dates=dates,
            asset_returns={"WEGE3": returns, "ITUB4": [r * 0.5 for r in returns]},
            portfolio_dates=dates,
            portfolio_returns=returns,
            asset_data_notes=["XPML11: preço do provedor fora de escala descartado em 14/01/2026"],
            portfolio_data_notes=["21/10/2025 (-415.6%)"],
        ),
        HealthPolicy(),
    )
    checks = {c.key: c for p in report.pillars for c in p.checks}
    for key in ASSET_SERIES_CHECKS & checks.keys():
        assert "XPML11" in (checks[key].suspicious or ""), key
    for key in PORTFOLIO_SERIES_CHECKS & checks.keys():
        assert "21/10/2025" in (checks[key].suspicious or ""), key
    assert checks["largest_asset"].suspicious is None
    risk = checks["risk_contribution"]
    assert risk.explanation.endswith("Por quadrante:") and len(risk.items) == 1
