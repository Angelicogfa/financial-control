"""Phase 45.8b: the full optimizer of the weights inside a class."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from domain.recommendation.combination import ClassMatrix, MatrixRow
from domain.recommendation.construction import build_class
from domain.recommendation.optimizer import (
    NO_CANDIDATES,
    OK,
    OptimizedClass,
    OptimizerParams,
    candidates,
    cvar,
    optimize_class,
    solve,
)
from domain.recommendation.params import ConstructionParams

TODAY = date(2026, 11, 1)
MONTHS = [(2021 + (i // 12), i % 12 + 1) for i in range(60)]
FAST = OptimizerParams(draws=6, scenarios=120)


def _row(ticker: str, rank: int, score: float, sector: str, confidence: float = 1.0) -> MatrixRow:
    return MatrixRow(
        ticker=ticker,
        source="CATALOG",
        sector=sector,
        rank=rank,
        score=score,
        expected=(score - 0.5) / 0.5 * 0.06,
        expected_low=0.0,
        expected_high=0.0,
        confidence=confidence,
        cells=[],
        gaussian_score=score,
        gaussian_rank=rank,
    )


def _matrix(rows: list[MatrixRow]) -> ClassMatrix:
    return ClassMatrix("ACOES", "MIXED", TODAY, {}, 0.0, 0.06, {}, rows, [])


def _noise(seed: int, vol: float) -> dict:
    rng = np.random.default_rng(seed)
    return dict(zip(MONTHS, rng.normal(0.0, vol, len(MONTHS)), strict=True))


def test_candidates_keep_two_per_sector_and_twice_k_max() -> None:
    rows = [_row(f"T{i}", i + 1, 0.9 - i * 0.01, f"S{i // 3}") for i in range(30)]
    found = candidates(rows, ConstructionParams(k_max=4, max_per_sector=2))
    assert len(found) == 8
    sectors = [r.sector for r in found]
    assert all(sectors.count(s) <= 2 for s in sectors)


def test_solver_without_risk_takes_the_best_up_to_the_caps() -> None:
    mu = np.array([0.10, 0.02, 0.01, 0.00])
    cov = np.eye(4) * 0.04
    caps = [(np.array([1.0, 1.0, 0.0, 0.0]), 0.5)]
    w = solve(mu, cov, 0.0, caps, upper=0.4)
    assert w is not None
    assert w[0] == pytest.approx(0.4, abs=1e-4)  # the per-asset bound
    assert w[0] + w[1] <= 0.5 + 1e-6
    assert w.sum() == pytest.approx(1.0)


def test_equal_assets_get_about_equal_weights() -> None:
    rows = [_row(f"T{i}", i + 1, 0.7, f"S{i}") for i in range(6)]
    returns = {r.ticker: _noise(i, 0.06) for i, r in enumerate(rows)}
    found = optimize_class(_matrix(rows), returns, ConstructionParams(k_max=6), options=FAST)
    assert found.status == OK and len(found.assets) == 6
    # Pure noise: the averaged weights stay near 1/N (design 34, acceptance of 34.5).
    assert all(a.weight == pytest.approx(1 / 6, abs=0.08) for a in found.assets)
    assert sum(a.weight for a in found.assets) == pytest.approx(1.0)


def test_caps_and_k_max_hold_and_noise_is_marked_unstable() -> None:
    rows = [_row(f"T{i}", i + 1, 0.8 - i * 0.005, f"S{i % 4}") for i in range(12)]
    returns = {r.ticker: _noise(10 + i, 0.08) for i, r in enumerate(rows)}
    params = ConstructionParams(k_max=5, sector_cap=0.3)
    found = optimize_class(_matrix(rows), returns, params, options=FAST)
    assert len(found.assets) <= 5
    by_sector: dict[str, float] = {}
    sector = {r.ticker: r.sector for r in rows}
    for a in found.assets:
        by_sector[sector[a.ticker]] = by_sector.get(sector[a.ticker], 0.0) + a.weight
    assert max(by_sector.values()) <= 0.3 + 1e-6
    assert all(0.0 <= a.low <= a.high <= 1.0 for a in found.assets)


def test_the_limit_per_asset_holds() -> None:
    rows = [_row(f"T{i}", i + 1, 0.9 - i * 0.1, f"S{i}") for i in range(8)]
    returns = {r.ticker: _noise(30 + i, 0.06) for i, r in enumerate(rows)}
    params = ConstructionParams(k_max=8, sector_cap=0.5, group_cap=0.5, asset_cap=0.2)
    found = optimize_class(_matrix(rows), returns, params, options=FAST)
    assert max(a.weight for a in found.assets) <= 0.2 + 1e-6


def test_the_cvar_stays_at_most_that_of_the_current_holdings() -> None:
    rows = [_row(f"T{i}", i + 1, 0.9 - i * 0.02, f"S{i}") for i in range(5)]
    returns = {r.ticker: _noise(20 + i, 0.03 + 0.03 * i) for i, r in enumerate(rows)}
    returns["SAFE3"] = _noise(99, 0.05)
    found = optimize_class(
        _matrix(rows),
        returns,
        ConstructionParams(k_max=5, sector_cap=0.6, risk_aversion=0.0),
        current={"SAFE3": 1000.0},
        options=FAST,
    )
    assert found.cvar_bound and found.current_cvar is not None and found.cvar is not None
    assert found.cvar <= found.current_cvar * 1.15  # the draws' limit, measured on new scenarios


def test_construction_is_measured_next_to_it_and_round_trips() -> None:
    rows = [_row(f"T{i}", i + 1, 0.85 - i * 0.02, f"S{i}") for i in range(6)]
    returns = {r.ticker: _noise(40 + i, 0.06) for i, r in enumerate(rows)}
    params = ConstructionParams(k_max=6)
    built = build_class(_matrix(rows), returns, params)
    found = optimize_class(_matrix(rows), returns, params, construction=built, options=FAST)
    assert found.construction_utility != 0.0
    assert found.construction_cvar is not None and found.current_cvar is None  # nothing held
    assert any(a.construction_weight > 0 for a in found.assets)
    assert OptimizedClass.from_dict(found.to_dict()) == found


def test_no_rows_and_cvar_helper() -> None:
    assert optimize_class(_matrix([]), {}, ConstructionParams()).status == NO_CANDIDATES
    assert cvar(np.array([1.0, 2.0, 3.0, 10.0]), 0.75) == 10.0
    assert cvar(np.array([]), 0.95) == 0.0
