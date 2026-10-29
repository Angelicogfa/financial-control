"""Phase 33.8: purged walk-forward, deflated Sharpe, PBO by CSCV and the Bayesian gate.

Known truths (design 8.2): pure noise gives PBO near 50% and a deflated Sharpe without
significance; a real edge passes.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from domain.shared.enums import SeriesUnit
from domain.simulation.data import index_symbol, tr_symbol
from domain.simulation.engine import BacktestPoint
from domain.simulation.robustness import variant_validation
from domain.simulation.validation import (
    bayesian_gate,
    deflated_sharpe,
    expected_max_sharpe,
    norm_cdf,
    norm_ppf,
    pbo_cscv,
    probabilistic_sharpe,
    purged_walk_forward,
    sharpe,
    validate_configurations,
)
from worker.jobs import run_pending_simulations_job


def test_normal_helpers() -> None:
    assert norm_cdf(0.0) == pytest.approx(0.5)
    assert norm_cdf(1.959964) == pytest.approx(0.975, abs=1e-6)
    assert norm_ppf(0.975) == pytest.approx(1.959964, abs=1e-5)
    with pytest.raises(ValueError):
        norm_ppf(1.0)


def test_purged_walk_forward_never_trains_on_overlapping_labels() -> None:
    splits = purged_walk_forward(100, min_train=40, test_size=12, label_horizon=12, embargo=3)
    assert splits[0].train.max() < 40 - 11 and splits[0].test[0] == 40
    for split in splits:
        # A training label at t covers t..t+11: it must end before the test starts.
        assert split.train.max() + 11 < split.test[0]
    starts = [s.test[0] for s in splits]
    assert all(b - a == 15 for a, b in zip(starts, starts[1:], strict=False))  # 12 + embargo
    assert splits[-1].test[-1] < 100


def test_expected_max_sharpe_grows_with_the_trials() -> None:
    assert expected_max_sharpe(1, 0.04) == 0.0
    few, many = expected_max_sharpe(10, 0.04), expected_max_sharpe(1000, 0.04)
    assert 0 < few < many
    # Monte Carlo check: the max of 100 standard normals is about 2.5.
    rng = np.random.default_rng(1)
    simulated = rng.standard_normal((20000, 100)).max(axis=1).mean()
    assert expected_max_sharpe(100, 1.0) == pytest.approx(simulated, rel=0.03)


def test_probabilistic_sharpe() -> None:
    assert probabilistic_sharpe(0.0, 0.0, 120, 0.0, 3.0) == pytest.approx(0.5)
    assert probabilistic_sharpe(0.3, 0.0, 120, 0.0, 3.0) > 0.99


def test_noise_gives_the_null_result() -> None:
    rng = np.random.default_rng(2)
    noise = {f"cfg{i}": rng.normal(0.0, 0.04, 240) for i in range(20)}
    report = validate_configurations(noise, reference=rng.normal(0.0, 0.04, 240), seed=1)
    assert not report.deflated.significant
    assert report.overfitting is not None and 0.3 <= report.overfitting.pbo <= 0.7
    assert not report.passed and "Sem evidência" in report.verdict


def test_a_real_edge_passes() -> None:
    rng = np.random.default_rng(3)
    configs = {f"cfg{i}": rng.normal(0.0, 0.04, 240) for i in range(9)}
    configs["edge"] = rng.normal(0.03, 0.04, 240)  # a monthly Sharpe of 0.75
    report = validate_configurations(configs, reference=np.zeros(240), seed=1)
    assert report.best == "edge"
    assert report.deflated.significant and report.overfitting is not None
    assert report.overfitting.pbo < 0.1
    assert report.gate is not None and report.gate.passed
    assert report.passed and report.best_sharpe_annual == pytest.approx(
        0.75 * math.sqrt(12), rel=0.25
    )


def test_more_trials_deflate_the_same_sharpe() -> None:
    rng = np.random.default_rng(4)
    series = rng.normal(0.008, 0.04, 120)
    sharpes = list(rng.normal(0.0, 0.08, 10))
    alone = deflated_sharpe(series, sharpes, n_trials=2)
    crowded = deflated_sharpe(series, sharpes, n_trials=500)
    assert crowded.expected_max > alone.expected_max
    assert crowded.probability < alone.probability


def test_pbo_needs_two_configurations_and_blocks() -> None:
    with pytest.raises(ValueError):
        pbo_cscv(np.zeros((40, 1)))
    result = pbo_cscv(np.random.default_rng(5).normal(size=(40, 3)), blocks=4)
    assert result.blocks == 4 and result.combinations == 6


def test_bayesian_gate() -> None:
    rng = np.random.default_rng(6)
    better = bayesian_gate(rng.normal(0.01, 0.02, 200), np.zeros(200), seed=1)
    assert better.passed and better.probability > 0.99
    same = bayesian_gate(rng.normal(0.0, 0.02, 200), rng.normal(0.0, 0.02, 200), seed=1)
    assert not same.passed
    assert sharpe([1.0]) == 0.0 and sharpe([1.0, 1.0]) == 0.0


def _points(returns: np.ndarray, start: date = date(2010, 1, 29)) -> list[BacktestPoint]:
    value, out = 1000.0, []
    day = start
    for i, r in enumerate([0.0, *returns]):
        if i:
            value *= 1.0 + r
        out.append(BacktestPoint(day, 0.0, 1000.0, value, 0.0, 0.0))
        day = (day.replace(day=1) + timedelta(days=62)).replace(day=1) - timedelta(days=1)
    return out


def test_variant_validation_on_stored_points() -> None:
    rng = np.random.default_rng(7)
    cdi = np.full(60, 0.008)
    points = {
        "strategy": _points(cdi + rng.normal(0.0, 0.03, 60)),
        "benchmark:CDI": _points(cdi),
        **{f"variant:{i}": _points(cdi + rng.normal(0.0, 0.03, 60)) for i in range(8)},
    }
    report = variant_validation(
        points,
        [f"variant:{i}" for i in range(8)],
        reference_key="strategy",
        cdi_key="benchmark:CDI",
        trials_total=40,
        seed=1,
    )
    assert report is not None and report.deflated.trials == 40
    assert report.deflated.observations == 60 and not report.passed
    short = {k: v[:10] for k, v in points.items()}
    assert (
        variant_validation(
            short,
            ["variant:0", "variant:1"],
            reference_key="strategy",
            cdi_key=None,
            trials_total=2,
        )
        is None
    )


def test_robustness_route_carries_the_validation(api: SimpleNamespace) -> None:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=3 * 365)
    days, day = [], start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    rng = np.random.default_rng(8)
    api.client.post(
        "/api/v1/assets", json={"ticker": "WEGE3", "name": "WEG", "asset_type": "STOCK_BR"}
    )
    with api.uow_factory() as uow:
        prices = 40.0 * np.cumprod(1.0 + rng.normal(0.0005, 0.015, len(days)))
        uow.market_series.upsert_points(
            tr_symbol("WEGE3"), list(zip(days, prices, strict=True)), unit=SeriesUnit.PRICE
        )
        uow.market_series.upsert_points(
            index_symbol("IBOV"),
            list(
                zip(
                    days,
                    100_000.0 * np.cumprod(1.0 + rng.normal(0.0004, 0.01, len(days))),
                    strict=True,
                )
            ),
            unit=SeriesUnit.INDEX_POINTS,
        )
        uow.market_series.upsert_points(
            "CDI", [(d, 0.04) for d in days], unit=SeriesUnit.PERCENT_PER_DAY
        )
        uow.commit()
    request = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "monthly_contribution": 1000.0,
        "benchmarks": ["CDI"],
        "variants": True,
    }
    run = api.client.post("/api/v1/simulations/backtests", json=request).json()
    run_pending_simulations_job(api.uow_factory, timeout_seconds=300)
    data = api.client.get(f"/api/v1/simulations/{run['id']}/robustness").json()
    validation = data["validation"]
    assert validation is not None
    assert validation["trials"] >= len(data["variants"])
    assert 0.0 <= validation["deflated_probability"] <= 1.0
    assert validation["pbo"] is not None and validation["verdict"]
