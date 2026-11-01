"""Phase 45.4: weights inside the class (dynamic K, sectors, groups) and the contribution."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from core.errors import ValidationError
from domain.policy.services.policy import RecommendationPolicy
from domain.recommendation.combination import ClassMatrix, MatrixRow
from domain.recommendation.construction import (
    ClassConstruction,
    SelectedAsset,
    allowed_now,
    build_class,
    correlation_groups,
    covariance,
    pulled_targets,
    set_weights,
)
from domain.recommendation.params import ConstructionParams

TODAY = date(2026, 10, 31)
MONTHS = [(2023 + (i // 12), i % 12 + 1) for i in range(36)]


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


def _returns(seed: int, factor: np.ndarray, beta: float, noise: float) -> dict:
    rng = np.random.default_rng(seed)
    values = beta * factor + rng.normal(0.0, noise, len(MONTHS))
    return dict(zip(MONTHS, values, strict=True))


def test_groups_join_assets_that_move_together() -> None:
    rng = np.random.default_rng(0)
    rates = rng.normal(0.0, 0.05, len(MONTHS))
    other = rng.normal(0.0, 0.05, len(MONTHS))
    returns = {
        "SANE3": _returns(1, rates, 1.0, 0.005),
        "ENER3": _returns(2, rates, 1.0, 0.005),  # another sector, same driver
        "TECH3": _returns(3, other, 1.0, 0.005),
    }
    groups = correlation_groups(returns, ["SANE3", "ENER3", "TECH3"])
    assert groups == {"SANE3": "SANE3", "ENER3": "SANE3", "TECH3": "TECH3"}
    cov = covariance(returns, ["SANE3", "ENER3", "TECH3"])
    assert cov[0, 1] > 0 and abs(cov[0, 2]) < cov[0, 1]
    assert covariance({}, ["X"])[0, 0] == pytest.approx(0.09)  # nothing known: 30% a year


def test_sector_rule_allows_a_covered_sector_only_above_the_margin() -> None:
    rows = [
        _row("BANK1", 1, 0.80, "Bancos"),
        _row("BANK2", 2, 0.79, "Bancos"),
        _row("AGRO1", 3, 0.70, "Agro"),
        _row("TECH1", 4, 0.40, "Tecnologia"),
    ]
    sectors = {r.ticker: r.sector for r in rows}
    left = rows[1:]  # BANK1 already chosen
    tight = allowed_now(left, sectors, {"Bancos": 1}, margin=0.05)
    assert [r.ticker for r in tight] == ["BANK2", "AGRO1", "TECH1"]  # 0.79 - 0.70 > 0.05
    wide = allowed_now(left, sectors, {"Bancos": 1}, margin=0.2)
    assert [r.ticker for r in wide] == ["AGRO1", "TECH1"]
    every = allowed_now(left[:1], sectors, {"Bancos": 1}, margin=0.2)
    assert [r.ticker for r in every] == ["BANK2"]  # no new sector left: anyone


def test_caps_per_sector_and_relaxed_when_infeasible() -> None:
    rows = [_row(f"A{i}", i, 0.9, "Bancos") for i in range(1, 3)] + [_row("B1", 3, 0.3, "Agro")]
    sectors = {r.ticker: r.sector for r in rows}
    groups = {r.ticker: r.ticker for r in rows}
    weights, notes = set_weights(rows, sectors, groups, ConstructionParams(sector_cap=0.25))
    assert sum(weights.values()) == pytest.approx(1.0)
    # Two sectors cannot hold 25% each: the sector cap goes to 50% and prevails over the group's.
    assert weights["A1"] + weights["A2"] == pytest.approx(0.5, abs=1e-6)
    assert any("teto usado de 50%" in n for n in notes)
    assert any("o de setor prevaleceu" in n for n in notes)


def test_build_class_prefers_diversifying_assets() -> None:
    rng = np.random.default_rng(5)
    common = rng.normal(0.0, 0.06, len(MONTHS))
    rows, returns = [], {}
    for i in range(8):
        ticker = f"S{i}"
        rows.append(_row(ticker, i + 1, 0.9 - 0.02 * i, f"Setor {i}"))
        # The first four move together; the others are independent.
        returns[ticker] = (
            _returns(10 + i, common, 1.0, 0.01) if i < 4 else _returns(10 + i, common, 0.0, 0.06)
        )
    built = build_class(_matrix(rows), returns, ConstructionParams(risk_aversion=0.5))
    chosen = [s.ticker for s in built.selected]
    assert chosen[0] in {"S0", "S1", "S2", "S3"} and 3 <= built.k <= 8
    assert {"S4", "S5"} & set(chosen)  # a diversifying asset beat S1's slightly higher score
    assert sum(s.weight for s in built.selected) == pytest.approx(1.0, abs=1e-5)
    assert len({s.group for s in built.selected}) >= 2
    assert all(s.reason for s in built.selected)
    assert [p.k for p in built.curve][: built.k] == list(range(1, built.k + 1))
    assert ClassConstruction.from_dict(built.to_dict()) == built
    assert build_class(_matrix([]), {}, ConstructionParams()).k == 0


def test_dynamic_k_limits() -> None:
    rows = [_row(f"T{i}", i + 1, 0.9 - 0.01 * i, f"Setor {i}") for i in range(6)]
    rng = np.random.default_rng(2)
    returns = {
        r.ticker: dict(zip(MONTHS, rng.normal(0.0, 0.05, len(MONTHS)), strict=True)) for r in rows
    }
    capped = build_class(_matrix(rows), returns, ConstructionParams(k_min=1, k_max=2))
    assert capped.k == 2 and "máximo de 2" in capped.stop_reason
    # A huge risk aversion stops at the minimum, saying who was refused.
    shy = build_class(_matrix(rows), returns, ConstructionParams(risk_aversion=0.0, k_min=3))
    assert shy.k >= 3
    few = build_class(_matrix(rows[:2]), returns, ConstructionParams(k_min=3))
    assert few.k == 2 and "o mínimo é 3" in few.stop_reason


def test_targets_are_pulled_toward_the_current_weights() -> None:
    built = ClassConstruction(
        "ACOES",
        TODAY,
        2,
        "",
        0.6,
        [
            SelectedAsset("NEW3", "X", "NEW3", 0.5, 0.8, 0.03, 1.0, ""),
            SelectedAsset("OLD3", "Y", "OLD3", 0.5, 0.7, 0.02, 1.0, ""),
        ],
        [],
        [],
    )
    targets = pulled_targets(built, {"OLD3": 600.0, "GONE3": 400.0})
    assert targets["NEW3"] == pytest.approx(0.6 * 0.5)
    assert targets["OLD3"] == pytest.approx(0.6 * 0.5 + 0.4 * 0.6)
    assert targets["GONE3"] == pytest.approx(0.4 * 0.4)  # held, not chosen: only its share left
    assert pulled_targets(built, {}) == {"NEW3": 0.5, "OLD3": 0.5}  # nothing held: no pull


def test_construction_parameters_in_the_policy() -> None:
    params = RecommendationPolicy().construction()
    assert (params.k_min, params.k_max, params.sector_cap, params.max_per_sector) == (
        3,
        12,
        0.25,
        2,
    )
    with pytest.raises(ValidationError):
        RecommendationPolicy(k_min=5, k_max=3)
    with pytest.raises(ValidationError):
        RecommendationPolicy(sector_cap=0.0)
    with pytest.raises(ValidationError):
        RecommendationPolicy(min_lot_brl=-1.0)
