"""Phase 33.5: forward projection (layer B) by stationary block bootstrap and rate scenarios."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from domain.agentic.services.catalog import CATALOG_BY_NAME, AgenticRuntimeHandlers
from domain.policy.services.assumptions import ProjectionAssumptions
from domain.policy.services.policy import ArcaPolicy, ClassPolicy, InvestmentPolicy
from domain.portfolio.services.service import PortfolioApplicationService
from domain.shared.enums import ArcaClass, SeriesUnit
from domain.simulation.data import index_symbol
from domain.simulation.engine import SimulationTimeout
from domain.simulation.entities import SimulationStatus
from domain.simulation.market import MarketHistory, PriceSeries
from domain.simulation.runs import (
    ProjectionInputs,
    ProjectionParams,
    income_yields,
    new_projection_run,
    run_projection_params,
)
from domain.simulation.scenarios import (
    CLASS_ORDER,
    ClassSample,
    InsufficientHistory,
    ProjectionConfig,
    _allocate,
    class_sample,
    project,
    projection_warnings,
    stationary_bootstrap_indices,
)
from domain.tax.services.comparator import RateScenario
from tests.conftest import offline_gateway
from worker.jobs import run_pending_simulations_job

A, RE, INT, CX = (
    ArcaClass.ACOES,
    ArcaClass.REAL_ESTATE,
    ArcaClass.ATIVOS_INTERNACIONAIS,
    ArcaClass.CAIXA,
)
ZERO_RATES = RateScenario("BASE", 0.0, 0.0)


def _sample(excess: np.ndarray, cdi: float = 0.0, classes=(A, CX)) -> ClassSample:
    months = tuple(date(2000 + i // 12, i % 12 + 1, 28) for i in range(len(excess)))
    return ClassSample(
        months=months, excess=excess, cdi=np.full(len(excess), cdi), classes=tuple(classes)
    )


def _constant(n: int = 60, equity: float = 0.0) -> ClassSample:
    excess = np.zeros((n, len(CLASS_ORDER)))
    excess[:, 0] = equity
    return _sample(excess)


def _config(**overrides) -> ProjectionConfig:
    base = {
        "horizon_months": 120,
        "monthly_contribution": 1000.0,
        "initial_by_class": {},
        "targets": {A: 1.0},
        "cash_income_tax_rate": 0.0,
        "fee_rate": 0.0,
        "paths": 200,
    }
    return ProjectionConfig(**{**base, **overrides})


# --- bootstrap ----------------------------------------------------------------------------------


def test_bootstrap_without_restarts_replays_the_history_in_order() -> None:
    rng = np.random.default_rng(1)
    idx = stationary_bootstrap_indices(12, 12, 5, float("inf"), rng)
    for row in idx:
        assert sorted(row.tolist()) == list(range(12))  # a rotation of the whole history
        assert all((b - a) % 12 == 1 for a, b in zip(row, row[1:], strict=False))


def test_bootstrap_blocks_have_the_requested_mean_length() -> None:
    idx = stationary_bootstrap_indices(500, 2000, 50, 8.0, np.random.default_rng(2))
    breaks = (np.diff(idx, axis=1) % 500 != 1).sum()
    mean_block = idx.size / (breaks + idx.shape[0])
    assert mean_block == pytest.approx(8.0, rel=0.1)


# --- known truths (design 8.2) -------------------------------------------------------------------


def test_constant_return_gives_the_closed_form_future_value() -> None:
    r = 0.01
    sample = _constant(equity=r)
    result = project(sample, ZERO_RATES, _config(initial_by_class={A: 5000.0}), seed=1)
    n = 120
    expected = 5000.0 * (1 + r) ** n + 1000.0 * ((1 + r) ** n - 1) / r
    final = result.final_wealth
    assert final.p5 == final.p95 == pytest.approx(expected, abs=0.01)
    assert result.contributed == pytest.approx(5000.0 + 1000.0 * n)
    assert result.max_drawdown.p50 == 0.0


def test_cash_earning_exactly_inflation_keeps_the_real_value() -> None:
    scenario = RateScenario("BASE", 0.06, 0.06)
    config = _config(targets={CX: 1.0}, initial_by_class={CX: 10_000.0})
    result = project(_constant(), scenario, config, seed=1)
    assert result.final_wealth.p50 == pytest.approx(result.contributed, rel=1e-9)
    assert result.final_income.p50 == pytest.approx(0.0, abs=1e-9)  # no real yield to live on
    assert result.final_net_wealth.p50 == pytest.approx(result.final_wealth.p50)


def test_the_same_seed_reproduces_and_another_seed_changes_the_paths() -> None:
    rng = np.random.default_rng(3)
    excess = np.zeros((120, 4))
    excess[:, 0] = rng.normal(0.004, 0.06, 120)
    sample = _sample(excess, cdi=0.008)
    config = _config(targets={A: 0.6, CX: 0.4}, initial_by_class={A: 10_000.0})
    scenario = RateScenario("BASE", 0.10, 0.04)
    first = project(sample, scenario, config, seed=7)
    assert project(sample, scenario, config, seed=7) == first
    assert project(sample, scenario, config, seed=8).final_wealth != first.final_wealth
    assert first.final_wealth.p5 < first.final_wealth.p50 < first.final_wealth.p95
    assert first.max_drawdown.p5 < 0


def test_contributions_go_to_the_classes_below_target() -> None:
    values = np.array([[900.0, 0.0, 0.0, 100.0]])
    bought = _allocate(values, np.array([1000.0]), np.array([0.5, 0.0, 0.0, 0.5]))
    # After the contribution the total is 2000: Ações already has 900 of its 1000.
    assert bought.tolist() == [[pytest.approx(100.0), 0.0, 0.0, pytest.approx(900.0)]]
    empty = _allocate(np.zeros((1, 4)), np.array([100.0]), np.array([0.25] * 4))
    assert empty.tolist() == [[25.0] * 4]


def test_rebalancing_pays_income_tax_on_the_gain_sold() -> None:
    sample = _constant(equity=0.03)  # stocks run away from the target every month
    base = _config(
        targets={A: 0.5, CX: 0.5},
        bands={A: 0.05, CX: 0.05},
        initial_by_class={A: 5000.0, CX: 5000.0},
        monthly_contribution=0.0,
        horizon_months=36,
    )
    held = project(sample, ZERO_RATES, base, seed=1)
    rebalanced = project(sample, ZERO_RATES, replace(base, rebalance=True), seed=1)
    assert held.taxes == 0.0 and rebalanced.taxes > 0
    # Without selling, the tax is only due on exit: the net wealth is below the gross.
    assert held.final_net_wealth.p50 < held.final_wealth.p50
    assert rebalanced.final_wealth.p50 < held.final_wealth.p50


def test_goals_probability_and_time() -> None:
    config = _config(wealth_goal=12_000.0, income_goal=1_000_000.0, income_yield={A: 0.12})
    result = project(_constant(), ZERO_RATES, config, seed=1)
    assert result.wealth_goal is not None and result.wealth_goal.probability == 1.0
    assert result.wealth_goal.standard_error == 0.0
    assert result.wealth_goal.months is not None and result.wealth_goal.months.p50 == 12
    assert result.income_goal is not None and result.income_goal.probability == 0.0
    assert result.income_goal.months is None
    # 120 contributions of 1000 at 12% a year paid out monthly.
    assert result.final_income.p50 == pytest.approx(120_000.0 * 0.01)


def test_the_deadline_stops_the_projection() -> None:
    with pytest.raises(SimulationTimeout):
        project(_constant(), ZERO_RATES, _config(), seed=1, deadline=lambda: True)


def test_higher_rates_raise_the_real_value_of_cash() -> None:
    sample = _constant()
    inputs = ProjectionInputs(
        sample=sample,
        policy=InvestmentPolicy(
            arca=ArcaPolicy(
                {c: ClassPolicy(target_pct=100.0 if c == CX else 0.0) for c in ArcaClass}
            )
        ),
    )
    params = ProjectionParams(
        horizon_years=10,
        monthly_contribution=1000.0,
        initial_by_class={},
        income_yield_by_class={},
        cdi_rate=0.10,
        ipca_rate=0.04,
        paths=100,
    )
    low, base, high = run_projection_params(inputs, params, seed=1)
    assert [low.scenario.name, base.scenario.name, high.scenario.name] == ["LOW", "BASE", "HIGH"]
    assert low.final_wealth.p50 < base.final_wealth.p50 < high.final_wealth.p50
    assert base.label == "Juros na premissa"


# --- sample and premises -------------------------------------------------------------------------


def _month_series(start: date, months: int, monthly: float, base: float = 100.0) -> PriceSeries:
    points, level, day = [], base, start
    for _ in range(months + 1):
        points.append((day, level))
        level *= 1.0 + monthly
        day = (day + timedelta(days=32)).replace(day=1)
    return PriceSeries.from_points(points)


def test_class_sample_measures_the_excess_over_the_cdi() -> None:
    start = date(2015, 1, 1)
    history = MarketHistory(
        {
            "CDI": _month_series(start, 48, 0.01),
            "IBOV": _month_series(start, 48, 0.02),
            "IFIX": _month_series(date(2017, 1, 1), 24, 0.0),
        }
    )
    sample = class_sample(history, [A, CX])
    assert sample.size >= 24 and sample.classes == (A, CX)
    assert sample.excess[:, 0] == pytest.approx(np.full(sample.size, 1.02 / 1.01 - 1.0))
    assert sample.excess[:, 1:].sum() == 0.0

    with pytest.raises(InsufficientHistory, match="SP500_BRL"):
        class_sample(history, [A, INT, CX])
    with pytest.raises(InsufficientHistory, match="24"):
        class_sample(history, [A, RE, CX])  # IFIX shortens the common window below 24 months


def test_income_yields_use_the_portfolio_and_fall_back_to_premises() -> None:
    yields = income_yields(
        {A: 10_000.0, RE: 0.0, INT: 1000.0},
        {A: 600.0, INT: 900.0},
        ProjectionAssumptions(real_estate_default_yield_rate=0.09),
    )
    assert yields[A] == pytest.approx(0.06)
    assert yields[RE] == pytest.approx(0.09)
    assert yields[INT] == pytest.approx(0.30)  # capped
    assert CX not in yields


def test_projection_warnings() -> None:
    sample = replace(_constant(30), limited_by="IFIX")
    warnings = projection_warnings(sample, _config(horizon_months=360))
    assert any("Amostra curta: 30 meses" in w for w in warnings)
    assert any("IFIX" in w for w in warnings)
    assert any("horizonte" in w for w in warnings)


def test_params_round_trip() -> None:
    params = ProjectionParams(
        horizon_years=20,
        monthly_contribution=1500.0,
        initial_by_class={"ACOES": 1000.0},
        income_yield_by_class={"ACOES": 0.05},
        cdi_rate=0.11,
        ipca_rate=0.045,
        wealth_goal=1e6,
        sample_start=date(2010, 1, 1),
    )
    assert ProjectionParams.from_dict(params.to_dict()) == params
    assert (
        new_projection_run(params).params_hash
        != new_projection_run(replace(params, monthly_contribution=1600.0)).params_hash
    )


# --- worker, routes and MCP ----------------------------------------------------------------------

TODAY = date.today()
REQUEST = {
    "horizon_years": 5,
    "monthly_contribution": 1000.0,
    "initial_by_class": {"ACOES": 10_000.0, "CAIXA": 5000.0},
    "cdi_rate": 0.10,
    "ipca_rate": 0.04,
    "wealth_goal": 50_000.0,
    "income_goal": 200.0,
    "paths": 300,
}


def _seed(api: SimpleNamespace) -> None:
    """Three years of daily IBOV and CDI and a policy with only Ações and Caixa."""
    days, day = [], TODAY - timedelta(days=3 * 365)
    while day <= TODAY:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    rng = np.random.default_rng(5)
    level, ibov = 100_000.0, []
    for d in days:
        level *= 1.0 + float(rng.normal(0.0006, 0.012))
        ibov.append((d, level))
    targets = {A: 60.0, CX: 40.0}
    with api.uow_factory() as uow:
        uow.market_series.upsert_points(index_symbol("IBOV"), ibov, unit=SeriesUnit.INDEX_POINTS)
        uow.market_series.upsert_points(
            "CDI", [(d, 0.04) for d in days], unit=SeriesUnit.PERCENT_PER_DAY
        )
        uow.policies.add(
            InvestmentPolicy(
                arca=ArcaPolicy({c: ClassPolicy(target_pct=targets.get(c, 0.0)) for c in ArcaClass})
            )
        )
        uow.commit()


def test_submit_run_and_read_the_projection(api: SimpleNamespace) -> None:
    _seed(api)
    response = api.client.post("/api/v1/simulations/projections", json=REQUEST)
    assert response.status_code == 202
    queued = response.json()
    assert queued["kind"] == "PROJECTION" and queued["status"] == "PENDING"
    params = queued["params"]
    assert params["cdi_rate"] == 0.10 and params["initial_by_class"]["ACOES"] == 10_000.0
    assert params["income_yield_by_class"]["ACOES"] == 0.05  # no position: the premise

    assert run_pending_simulations_job(api.uow_factory, timeout_seconds=60) == {"DONE": 1}
    run_id = queued["id"]
    detail = api.client.get(f"/api/v1/simulations/{run_id}").json()
    assert detail["status"] == "DONE" and detail["results"] == []

    data = api.client.get(f"/api/v1/simulations/{run_id}/projection").json()
    assert [s["key"] for s in data["scenarios"]] == [
        "projection:LOW",
        "projection:BASE",
        "projection:HIGH",
    ]
    base = data["scenarios"][1]
    assert [p["month"] for p in base["points"]] == [0, 12, 24, 36, 48, 60]
    assert base["points"][0]["wealth"]["p50"] == pytest.approx(15_000.0)
    assert base["contributed"] == pytest.approx(15_000.0 + 60 * 1000.0)
    assert 0.0 <= base["wealth_goal"]["probability"] <= 1.0
    assert [p["arca_class"] for p in base["premises"]] == ["ACOES", "CAIXA"]
    assert data["classes"] == ["ACOES", "CAIXA"] and data["sample_months"] >= 24
    assert data["targets"]["ACOES"] == 60.0
    assert any("Simulação, não recomendação" in w for w in data["warnings"])

    kinds = api.client.get("/api/v1/simulations", params={"kind": "PROJECTION"}).json()
    assert [r["id"] for r in kinds] == [run_id]
    assert api.client.get("/api/v1/simulations", params={"kind": "BACKTEST"}).json() == []
    assert api.client.get(f"/api/v1/simulations/{run_id}/robustness").status_code == 400


def test_the_same_projection_is_reused(api: SimpleNamespace) -> None:
    _seed(api)
    first = api.client.post("/api/v1/simulations/projections", json=REQUEST).json()
    second = api.client.post("/api/v1/simulations/projections", json=REQUEST).json()
    run_pending_simulations_job(api.uow_factory, timeout_seconds=60)
    a = api.client.get(f"/api/v1/simulations/{first['id']}/projection").json()
    b = api.client.get(f"/api/v1/simulations/{second['id']}/projection").json()
    assert a["scenarios"] == b["scenarios"]
    assert (
        api.client.get(f"/api/v1/simulations/{second['id']}").json()["reused_from"] == first["id"]
    )


def test_missing_history_fails_the_run(api: SimpleNamespace) -> None:
    api.client.post("/api/v1/simulations/projections", json=REQUEST)
    assert run_pending_simulations_job(api.uow_factory, timeout_seconds=60) == {"FAILED": 1}
    failed = api.client.get("/api/v1/simulations").json()[0]
    assert "InsufficientHistory" in failed["error"]
    data = api.client.get(f"/api/v1/simulations/{failed['id']}/projection").json()
    assert data["status"] == "FAILED" and data["scenarios"] == []


def test_projection_request_validation(api: SimpleNamespace) -> None:
    post = api.client.post
    url = "/api/v1/simulations/projections"
    empty = {**REQUEST, "initial_by_class": {}, "monthly_contribution": 0}
    assert post(url, json=empty).json()["code"] == "EMPTY_PROJECTION"
    assert post(url, json={**REQUEST, "horizon_years": 0}).status_code == 422
    assert post(url, json={**REQUEST, "paths": 10_000}).status_code == 422
    assert post(url, json={**REQUEST, "initial_by_class": {"XPTO": 1.0}}).status_code == 422

    with api.uow_factory() as uow:
        backtest = uow.simulations.list_recent(1)
    assert backtest == []
    assert api.client.get("/api/v1/simulations/999/projection").status_code == 404


def test_starting_point_comes_from_the_portfolio(api: SimpleNamespace) -> None:
    request = {k: v for k, v in REQUEST.items() if k not in ("initial_by_class", "cdi_rate")}
    run = api.client.post("/api/v1/simulations/projections", json=request).json()
    params = run["params"]
    # An empty portfolio starts at zero in every class; the CDI comes from the market.
    assert set(params["initial_by_class"]) == {c.value for c in ArcaClass}
    assert sum(params["initial_by_class"].values()) == 0.0
    assert params["cdi_rate"] > 0 and params["ipca_rate"] == 0.04


def test_mcp_operations(api: SimpleNamespace) -> None:
    _seed(api)
    handlers = AgenticRuntimeHandlers(
        uow_factory=api.uow_factory,
        portfolio_service=PortfolioApplicationService(offline_gateway()),
    )
    submit = CATALOG_BY_NAME["simulation.project"]
    assert submit.kind == "command"
    run = submit.invoke(handlers, submit.input_model(**REQUEST))
    run_pending_simulations_job(api.uow_factory, timeout_seconds=60)
    read = CATALOG_BY_NAME["simulation.projection"]
    data = read.invoke(handlers, read.input_model(run_id=run.id))
    assert data.status == SimulationStatus.DONE and len(data.scenarios) == 3
    listing = CATALOG_BY_NAME["simulation.list"]
    assert listing.invoke(handlers, listing.input_model(kind="BACKTEST")) == []
