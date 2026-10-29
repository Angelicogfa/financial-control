"""Phase 33.9: machine learning laboratory (regime and risk only) with out-of-sample gates.

Known truths: iid noise passes no model ("no model passed" is a valid result); data with real
regimes and volatility clustering is recognized by the regime and risk models.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from domain.agentic.services.catalog import CATALOG_BY_NAME, AgenticRuntimeHandlers
from domain.policy.services.policy import ArcaPolicy, ClassPolicy, InvestmentPolicy
from domain.portfolio.services.service import PortfolioApplicationService
from domain.shared.enums import ArcaClass, SeriesUnit
from domain.simulation.data import index_symbol
from domain.simulation.ml.lab import run_lab
from domain.simulation.ml.models import (
    MODELS,
    fit_garch,
    fit_hmm,
    fit_mixture,
    forecast_logscores,
    hmm_filter,
    normal_logpdf,
)
from domain.simulation.scenarios import ClassSample, InsufficientHistory
from tests.conftest import offline_gateway
from worker.jobs import run_pending_simulations_job

A, CX = ArcaClass.ACOES, ArcaClass.CAIXA


def _regimes(n: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    state, states, values = 0, [], []
    for _ in range(n):
        if rng.random() < 0.04:
            state = 1 - state
        states.append(state)
        values.append(rng.normal(0.01, 0.02) if state == 0 else rng.normal(-0.02, 0.10))
    return np.array(values), np.array(states)


def _sample(values: np.ndarray) -> ClassSample:
    t = values.size
    excess = np.zeros((t, 4))
    excess[:, 0] = values
    months = tuple(date(2000 + i // 12, i % 12 + 1, 28) for i in range(t))
    return ClassSample(months=months, excess=excess, cdi=np.full(t, 0.008), classes=(A, CX))


def test_hmm_recovers_two_regimes_and_filters_them() -> None:
    y, states = _regimes(400, 1)
    p = fit_hmm(y, 2)
    assert p.means[0] < p.means[1]  # state 0 is the worst regime
    assert math.sqrt(p.variances[0]) == pytest.approx(0.10, rel=0.3)
    assert math.sqrt(p.variances[1]) == pytest.approx(0.02, rel=0.3)
    assert np.diag(p.transition).min() > 0.85  # sticky regimes
    stress = hmm_filter(y, p)[:, 0]
    assert ((stress > 0.5) == (states == 1)).mean() > 0.85


def test_mixture_and_garch() -> None:
    rng = np.random.default_rng(2)
    y = np.concatenate([rng.normal(-0.05, 0.02, 300), rng.normal(0.03, 0.02, 700)])
    m = fit_mixture(y, 2)
    assert sorted(np.round(m.means, 2).tolist()) == [-0.05, 0.03]
    assert sorted(np.round(m.weights, 1).tolist()) == [0.3, 0.7]
    # GARCH(1,1) data: high persistence.
    var, values = 0.0004, []
    for _ in range(2000):
        r = rng.normal(0.0, math.sqrt(var))
        values.append(r)
        var = 0.00002 + 0.1 * r * r + 0.85 * var
    _, _, a, b = fit_garch(np.array(values))
    assert a + b > 0.85


def test_the_reference_is_the_normal_of_the_past() -> None:
    y = np.random.default_rng(3).normal(0.0, 0.05, 80)
    scores = forecast_logscores(y, None, start=60)
    assert scores[0] == pytest.approx(normal_logpdf(y[60], y[:60].mean(), y[:60].var(ddof=1)))
    assert len(MODELS) == 6 and {m.family for m in MODELS} == {"REGIME", "RISK"}


def test_noise_passes_no_model() -> None:
    y = np.random.default_rng(4).normal(0.004, 0.05, 200)
    result = run_lab(_sample(y), {A: 1.0}, prior_trials=0, seed=1)
    assert result.approved == []
    assert result.verdict.startswith("Nenhum modelo passou")
    assert result.trials == 6 and all(m.reasons for m in result.models)
    assert len(result.regime) == 200
    # Phase 41.1: every model carries its own gain curve, so the chart follows the table.
    assert set(result.cumulative_gains) == {m.key for m in result.models}
    curve = result.cumulative_gains[result.models[0].key]
    assert len(curve) == result.models[0].months
    assert abs(curve[-1][1] - result.models[0].mean_gain * result.models[0].months) < 1e-2


def test_real_regimes_are_recognized() -> None:
    # The gates are strict: with 240 months not every sample of regime data passes all of
    # them (seeds 5, 9 and 10 fail one gate); this one has clear regimes.
    y, _ = _regimes(240, 7)
    result = run_lab(_sample(y), {A: 1.0}, prior_trials=0, seed=1)
    assert "HMM2" in result.approved
    hmm2 = next(m for m in result.models if m.key == "HMM2")
    assert hmm2.gate_probability >= 0.95 and hmm2.stable and hmm2.mean_gain > 0
    assert result.verdict.startswith("Passaram")


def test_more_trials_raise_the_bar_and_short_history_fails() -> None:
    y, _ = _regimes(240, 6)
    few = run_lab(_sample(y), {A: 1.0}, prior_trials=0, seed=1)
    many = run_lab(_sample(y), {A: 1.0}, prior_trials=10_000, seed=1)
    assert many.trials == 10_006
    for a, b in zip(few.models, many.models, strict=True):
        assert b.deflated_probability <= a.deflated_probability
    with pytest.raises(InsufficientHistory):
        run_lab(_sample(y[:80]), {A: 1.0}, prior_trials=0, seed=1)


# --- worker, routes and MCP ----------------------------------------------------------------------


def _seed(api: SimpleNamespace) -> None:
    today = date.today()
    days, day = [], today - timedelta(days=9 * 365)
    while day <= today:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    rng = np.random.default_rng(7)
    ibov = 100_000.0 * np.cumprod(1.0 + rng.normal(0.0004, 0.012, len(days)))
    with api.uow_factory() as uow:
        uow.market_series.upsert_points(
            index_symbol("IBOV"), list(zip(days, ibov, strict=True)), unit=SeriesUnit.INDEX_POINTS
        )
        uow.market_series.upsert_points(
            "CDI", [(d, 0.04) for d in days], unit=SeriesUnit.PERCENT_PER_DAY
        )
        targets = {A: 60.0, CX: 40.0}
        uow.policies.add(
            InvestmentPolicy(
                arca=ArcaPolicy({c: ClassPolicy(target_pct=targets.get(c, 0.0)) for c in ArcaClass})
            )
        )
        uow.commit()


def test_lab_runs_in_the_worker_and_counts_the_trials(api: SimpleNamespace) -> None:
    assert api.client.get("/api/v1/simulations/lab").json()["run_id"] is None
    _seed(api)
    first = api.client.post("/api/v1/simulations/lab")
    assert first.status_code == 202 and first.json()["kind"] == "LAB"
    assert api.client.post("/api/v1/simulations/lab").json()["id"] == first.json()["id"]
    assert api.client.get("/api/v1/simulations/lab").json()["pending_run_id"] == first.json()["id"]

    assert run_pending_simulations_job(api.uow_factory, timeout_seconds=300) == {"DONE": 1}
    data = api.client.get("/api/v1/simulations/lab").json()
    assert data["status"] == "DONE" and data["trials"] == 6
    assert [m["key"] for m in data["models"]] == [m.key for m in MODELS]
    assert data["regime"] and 0.0 <= data["regime"][-1]["stress_probability"] <= 1.0
    assert data["verdict"]
    assert all(m["cumulative_gain"] for m in data["models"])

    api.client.post("/api/v1/simulations/lab")
    run_pending_simulations_job(api.uow_factory, timeout_seconds=300)
    # Same inputs: reused, not a new trial.
    assert api.client.get("/api/v1/simulations/lab").json()["trials"] == 6


def test_lab_mcp(api: SimpleNamespace) -> None:
    _seed(api)
    handlers = AgenticRuntimeHandlers(
        uow_factory=api.uow_factory,
        portfolio_service=PortfolioApplicationService(offline_gateway()),
    )
    submit = CATALOG_BY_NAME["simulation.run_lab"]
    assert submit.kind == "command"
    run = submit.invoke(handlers, submit.input_model())
    run_pending_simulations_job(api.uow_factory, timeout_seconds=300)
    read = CATALOG_BY_NAME["simulation.lab"]
    assert read.invoke(handlers, read.input_model(run_id=run.id)).status == "DONE"
