"""Unit tests for the Phase 29 statistics: risk metrics, diversification and accounting scores.

Synthetic series with known results: equal weights, a single asset, independent assets.
"""

from __future__ import annotations

import math
import random
from datetime import date, timedelta

import numpy as np
import pytest

from domain.assets.services.history import FundamentalPeriod, FundamentalSnapshot
from domain.assets.services.scores import (
    accounting_scores,
    altman_z_double_prime,
    piotroski_f_score,
)
from domain.portfolio.services.diversification import (
    concentration,
    decompose_risk,
    estimate_covariance,
    ledoit_wolf_shrinkage,
    sample_correlations,
    top_weight,
)
from domain.portfolio.services.risk_metrics import (
    bootstrap_intervals,
    class_time_weighted_returns,
    consistency_against,
    days_out_of_band,
    drawdown_state,
    historical_stress,
    information_ratio,
    monthly_returns,
    omega_ratio,
    rolling_windows,
    tracking_error,
    ulcer_index,
    weighted_returns,
)
from domain.shared.entities import PortfolioSnapshotEntity

START = date(2024, 1, 1)


def _dates(n: int) -> list[date]:
    return [START + timedelta(days=i) for i in range(n)]


def _noise(n: int, seed: int, scale: float = 0.01) -> list[float]:
    rng = random.Random(seed)
    return [rng.gauss(0.0, scale) for _ in range(n)]


# --- risk metrics ---------------------------------------------------------------------------


def test_drawdown_state_measures_depth_and_duration_since_peak() -> None:
    returns = [0.10, -0.10, 0.05]
    state = drawdown_state(_dates(3), returns)

    assert state.current == pytest.approx((1.1 * 0.9 * 1.05 - 1.1) / 1.1)
    assert state.periods == 2
    assert state.peak_date == START


def test_drawdown_state_at_peak_and_empty() -> None:
    assert drawdown_state(_dates(2), [0.01, 0.02]).current == 0.0
    assert drawdown_state(_dates(2), [0.01, 0.02]).periods == 0
    assert drawdown_state([], []).periods == 0


def test_ulcer_index_is_zero_without_losses_and_grows_with_depth() -> None:
    assert ulcer_index([0.01, 0.02]) == 0.0
    shallow = ulcer_index([-0.01, 0.0, 0.0])
    deep = ulcer_index([-0.10, 0.0, 0.0])
    assert deep > shallow > 0
    assert deep == pytest.approx(0.10)


def test_tracking_error_and_information_ratio_against_benchmark() -> None:
    bench = _noise(300, 1)
    active = [0.0004 + x for x in _noise(300, 2, 0.002)]
    returns = [b + a for b, a in zip(bench, active, strict=True)]

    te = tracking_error(returns, bench)
    ir = information_ratio(returns, bench)

    expected_te = float(np.std(active, ddof=1)) * math.sqrt(252)
    assert te == pytest.approx(expected_te)
    assert ir == pytest.approx(float(np.mean(active)) * 252 / expected_te)


def test_tracking_error_ignores_gaps_and_identical_series_has_no_ratio() -> None:
    returns = [0.01, 0.02, 0.03]
    assert tracking_error(returns, [None, None, 0.03]) is None
    assert information_ratio(returns, returns) is None


def test_omega_ratio_with_scalar_and_series_thresholds() -> None:
    assert omega_ratio([0.02, -0.01]) == pytest.approx(2.0)
    assert omega_ratio([0.02, -0.01], [0.01, None]) is None
    assert omega_ratio([0.03, 0.0], [0.01, 0.01]) == pytest.approx(2.0)
    assert omega_ratio([]) is None


def test_rolling_windows_need_a_full_window_and_include_the_last_period() -> None:
    returns = [0.001] * 300
    points = rolling_windows(_dates(300), returns, window=252, step=21)

    assert rolling_windows(_dates(100), returns[:100]) == []
    assert points[0].end == START + timedelta(days=251)
    assert points[-1].end == START + timedelta(days=299)
    assert points[-1].cumulative_return == pytest.approx(1.001**252 - 1, abs=1e-4)


def test_monthly_returns_and_consistency_against_cdi() -> None:
    dates = [date(2024, 1, 10), date(2024, 1, 20), date(2024, 2, 10), date(2024, 3, 10)]
    returns = [0.01, 0.01, -0.01, 0.02]
    cdi = [0.001, 0.001, 0.001, None]

    months = monthly_returns(dates, returns)
    share, compared = consistency_against(dates, returns, cdi)

    assert months["2024-01"] == pytest.approx(1.01**2 - 1)
    assert compared == 2
    assert share == 0.5


def test_weighted_returns_replays_fixed_weights_with_gaps_as_flat() -> None:
    out = weighted_returns({"A": 0.5, "B": 0.5}, {"A": [0.02, None], "B": [0.0, 0.04]})
    assert out == pytest.approx([0.01, 0.02])


def test_historical_stress_finds_worst_window() -> None:
    returns = [0.0] * 30 + [-0.01] * 21 + [0.0] * 30
    result = historical_stress(_dates(len(returns)), returns, window=21)

    assert result is not None
    assert result.worst_window_return == pytest.approx(0.99**21 - 1, abs=1e-4)
    assert result.window_start == START + timedelta(days=30)
    assert historical_stress(_dates(5), [0.0] * 5, window=21) is None


def test_bootstrap_is_deterministic_and_brackets_the_estimate() -> None:
    returns = [0.0008 + x for x in _noise(250, 3)]
    first = bootstrap_intervals(returns, samples=300)
    second = bootstrap_intervals(returns, samples=300)

    assert first == second
    assert first is not None
    sharpe_ci, cagr_ci = first
    assert sharpe_ci.low < sharpe_ci.high
    assert cagr_ci.low < cagr_ci.high
    assert bootstrap_intervals([0.01]) is None


def _snap(day: int, by_class: dict) -> PortfolioSnapshotEntity:
    return PortfolioSnapshotEntity(
        snapshot_date=START + timedelta(days=day),
        invested_value=0.0,
        market_value=0.0,
        unrealized_pnl=0.0,
        by_class=by_class,
    )


def test_class_twr_removes_contributions_from_the_return() -> None:
    snapshots = [
        _snap(0, {"ACOES": {"invested_value": 100.0, "current_value": 100.0}}),
        _snap(1, {"ACOES": {"invested_value": 100.0, "current_value": 110.0}}),
        _snap(2, {"ACOES": {"invested_value": 150.0, "current_value": 160.0}}),
    ]
    assert class_time_weighted_returns(snapshots) == {"ACOES": pytest.approx(0.10)}


def test_days_out_of_band_counts_the_current_streak_only() -> None:
    outside = {"current_pct": 40.0, "target_pct": 25.0}
    inside = {"current_pct": 26.0, "target_pct": 25.0}
    snapshots = [
        _snap(0, {"ACOES": outside}),
        _snap(1, {"ACOES": inside}),
        _snap(2, {"ACOES": outside}),
        _snap(3, {"ACOES": outside}),
    ]
    as_of = START + timedelta(days=3)

    assert days_out_of_band(snapshots, {"ACOES": 5.0}, as_of) == {"ACOES": 1}
    assert days_out_of_band(snapshots, {"ACOES": 20.0}, as_of) == {}


# --- diversification ------------------------------------------------------------------------


def test_concentration_of_equal_weights_and_single_asset() -> None:
    equal = concentration({"A": 10.0, "B": 10.0, "C": 10.0, "D": 10.0})
    single = concentration({"A": 10.0, "B": 0.0})

    assert equal is not None and single is not None
    assert equal.hhi == 0.25
    assert equal.effective_count == 4.0
    assert single.hhi == 1.0
    assert single.effective_count == 1.0
    assert concentration({}) is None
    assert top_weight({"A": 0.5, "B": 0.3, "C": 0.2}, 2) == pytest.approx(0.8)


def test_ledoit_wolf_shrinks_noise_fully_and_a_factor_model_partially() -> None:
    noise = np.array([_noise(40, s) for s in range(10)]).T
    factor = np.array(_noise(40, 99))
    correlated = noise + factor[:, None]

    _, pure_noise = ledoit_wolf_shrinkage(noise / noise.std(axis=0, ddof=1))
    shrunk, intensity = ledoit_wolf_shrinkage(correlated / correlated.std(axis=0, ddof=1))

    assert pure_noise == 1.0
    assert 0.0 < intensity < 1.0
    assert shrunk.shape == (10, 10)
    assert np.allclose(shrunk, shrunk.T)


def test_independent_equal_volatility_assets_diversify_by_sqrt_n() -> None:
    n_assets = 4
    series = {f"A{i}": _noise(2000, 10 + i) for i in range(n_assets)}
    estimate = estimate_covariance(series, min_observations=60)
    assert estimate is not None

    risk = decompose_risk(estimate, dict.fromkeys(series, 1.0))

    assert risk.diversification_ratio == pytest.approx(math.sqrt(n_assets), rel=0.08)
    assert sum(risk.risk_shares.values()) == pytest.approx(1.0, abs=1e-3)
    for share in risk.risk_shares.values():
        assert share == pytest.approx(0.25, abs=0.05)


def test_single_risky_asset_has_ratio_one_and_all_the_risk() -> None:
    series = {"STOCK": _noise(300, 5), "CDB": [0.0004] * 300}
    estimate = estimate_covariance(series, min_observations=60)
    assert estimate is not None

    risk = decompose_risk(estimate, {"STOCK": 50.0, "CDB": 50.0})

    assert risk.diversification_ratio == pytest.approx(1.0)
    assert risk.risk_shares["STOCK"] == pytest.approx(1.0)
    assert risk.risk_shares["CDB"] == 0.0
    stock_vol = float(np.std(series["STOCK"], ddof=1)) * math.sqrt(252)
    assert risk.volatility == pytest.approx(0.5 * stock_vol, rel=1e-3)


def test_assets_without_enough_history_are_left_out() -> None:
    series = {"A": _noise(100, 1), "B": [None] * 90 + _noise(10, 2)}
    estimate = estimate_covariance(series, min_observations=60)

    assert estimate is not None
    assert estimate.names == ["A"]
    assert estimate_covariance({"A": _noise(10, 1)}, min_observations=60) is None


def test_sample_correlations_flag_twin_assets() -> None:
    base = _noise(200, 7)
    series = {"A": base, "B": [x * 1.1 for x in base], "C": _noise(200, 8)}
    pairs = sample_correlations(series, ["A", "B", "C"])

    assert pairs[("A", "B")] == pytest.approx(1.0)
    assert abs(pairs[("A", "C")]) < 0.3


# --- accounting scores ----------------------------------------------------------------------


def _statement(year: int, **metrics: float) -> FundamentalSnapshot:
    return FundamentalSnapshot(
        ticker="WEGE3",
        reference_date=date(year, 12, 31),
        period=FundamentalPeriod.ANNUAL,
        metrics=metrics,
    )


PREV = {
    "net_income": 100.0,
    "total_assets": 1000.0,
    "operating_cash_flow": 120.0,
    "long_term_debt": 300.0,
    "current_assets": 400.0,
    "current_liabilities": 300.0,
    "shares_outstanding": 100.0,
    "gross_profit": 300.0,
    "revenue": 1000.0,
}
IMPROVED = {
    "net_income": 150.0,
    "total_assets": 1000.0,
    "operating_cash_flow": 200.0,
    "long_term_debt": 200.0,
    "current_assets": 500.0,
    "current_liabilities": 300.0,
    "shares_outstanding": 100.0,
    "gross_profit": 400.0,
    "revenue": 1100.0,
}


def test_piotroski_scores_nine_when_every_signal_improves() -> None:
    assert piotroski_f_score([_statement(2023, **PREV), _statement(2024, **IMPROVED)]) == 9


def test_piotroski_scores_low_when_everything_worsens() -> None:
    worse = {
        **PREV,
        "net_income": -10.0,
        "operating_cash_flow": -20.0,
        "long_term_debt": 400.0,
        "current_assets": 300.0,
        "shares_outstanding": 120.0,
        "gross_profit": 200.0,
        "revenue": 900.0,
    }
    assert piotroski_f_score([_statement(2023, **PREV), _statement(2024, **worse)]) == 0


def test_scores_need_their_statement_lines() -> None:
    partial = {"net_income": 1.0, "revenue": 2.0, "equity": 3.0}
    assert piotroski_f_score([_statement(2023, **partial), _statement(2024, **partial)]) is None
    assert piotroski_f_score([_statement(2024, **IMPROVED)]) is None
    assert altman_z_double_prime([_statement(2024, **partial)]) is None
    assert accounting_scores([]).z_zone is None


def test_altman_z_double_prime_formula_and_zones() -> None:
    lines = {
        "current_assets": 500.0,
        "current_liabilities": 300.0,
        "total_assets": 1000.0,
        "retained_earnings": 200.0,
        "ebit": 150.0,
        "equity": 400.0,
        "total_liabilities": 600.0,
    }
    z = altman_z_double_prime([_statement(2024, **lines)])

    expected = 6.56 * 0.2 + 3.26 * 0.2 + 6.72 * 0.15 + 1.05 * (400 / 600)
    assert z == pytest.approx(round(expected, 2))
    assert accounting_scores([_statement(2024, **lines)]).z_zone == "SAFE"
    distressed = {**lines, "current_assets": 100.0, "retained_earnings": -300.0, "ebit": -50.0}
    assert accounting_scores([_statement(2024, **distressed)]).z_zone == "DISTRESS"
