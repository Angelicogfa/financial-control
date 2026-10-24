"""Unit tests for date-aligned analytics and income-aware TWR (finding I-09)."""

from __future__ import annotations

from datetime import date

import pytest
from fincontrol_core.analytics import (
    align_to_base,
    analyze_return_series,
    dated_simple_returns,
    dated_time_weighted_returns,
    pearson_correlation,
)
from fincontrol_core.domain.entities import PortfolioSnapshotEntity

D = [date(2025, 1, d) for d in (2, 3, 6, 7, 8)]


def _snap(day: date, value: float, flow: float = 0.0, earnings: float = 0.0):
    return PortfolioSnapshotEntity(
        snapshot_date=day,
        invested_value=value,
        market_value=value,
        unrealized_pnl=0.0,
        earnings_cum=earnings,
        net_flow=flow,
    )


def test_dated_twr_removes_flows_adds_income_and_skips_empty_start() -> None:
    snapshots = [
        _snap(D[0], 0.0),
        _snap(D[1], 1000.0, flow=1000.0),
        _snap(D[2], 1600.0, flow=500.0, earnings=10.0),
    ]

    dates, returns = dated_time_weighted_returns(snapshots)

    assert dates == [D[2]]
    assert returns == [pytest.approx((1600 - 1000 - 500 + 10) / 1000)]


def test_dated_simple_returns_are_dated_by_period_end() -> None:
    dates, returns = dated_simple_returns(D[:3], [100.0, 110.0, 99.0])
    assert dates == [D[1], D[2]]
    assert returns == [pytest.approx(0.10), pytest.approx(-0.10)]


def test_align_to_base_compounds_and_marks_gaps() -> None:
    base_dates = [D[1], D[2], D[4]]
    other_dates = [D[1], D[2], D[3], D[4]]
    other_returns = [0.01, 0.02, 0.10, -0.05]

    aligned = align_to_base(base_dates, other_dates, other_returns)

    assert aligned[0] == pytest.approx(0.01)
    assert aligned[1] == pytest.approx(0.02)
    assert aligned[2] == pytest.approx(1.10 * 0.95 - 1)
    assert align_to_base([D[0], D[1]], [D[1]], [0.03]) == [None, pytest.approx(0.03)]


def test_pearson_ignores_gaps() -> None:
    assert pearson_correlation([0.01, 0.02, 0.03, 0.5], [0.02, 0.04, 0.06, None]) == (
        pytest.approx(1.0)
    )
    assert pearson_correlation([0.01, None], [0.02, 0.03]) is None


def test_benchmark_return_uses_aligned_window_only() -> None:
    summary = analyze_return_series(
        [0.01, 0.01],
        dates=[D[2], D[3]],
        benchmark_returns_map={"IBOV": [0.50, 0.02, 0.03]},
        benchmark_dates_map={"IBOV": [D[1], D[2], D[3]]},
    )

    ibov = next(b for b in summary.benchmarks if b.benchmark == "IBOV")
    # The 50% move on 01-03 precedes the portfolio window and must not count.
    assert ibov.benchmark_return == pytest.approx(1.02 * 1.03 - 1, abs=1e-4)
