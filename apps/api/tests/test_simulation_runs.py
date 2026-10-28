"""Phase 33.3: stored simulation runs, worker execution, reproducibility and time limit."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from domain.agentic.services.catalog import CATALOG_BY_NAME, AgenticRuntimeHandlers
from domain.policy.services.policy import InvestmentPolicy
from domain.portfolio.services.service import PortfolioApplicationService
from domain.shared.enums import ArcaClass, AssetType, SeriesUnit
from domain.simulation.data import index_symbol, tr_symbol
from domain.simulation.engine import (
    ENGINE_VERSION,
    BacktestConfig,
    SimulatedAsset,
    SimulationTimeout,
    run_backtest,
    run_benchmark,
)
from domain.simulation.entities import SimulationResult, SimulationStatus
from domain.simulation.market import MarketHistory, PriceSeries, month_ends
from domain.simulation.runs import (
    CASH_TICKER,
    BacktestParams,
    data_hash,
    execute_next_run,
    new_backtest_run,
    params_hash,
)
from tests.conftest import offline_gateway
from worker.jobs import run_pending_simulations_job
from worker.scheduler import _when_pending

START = date(2024, 1, 2)
END = date(2024, 6, 28)
REQUEST = {
    "start": START.isoformat(),
    "end": END.isoformat(),
    "monthly_contribution": 1000.0,
    "benchmarks": ["CDI", "IBOV"],
}


def _weekdays(start: date, end: date) -> list[date]:
    days, day = [], start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def _seed(api: SimpleNamespace, *, wege_drift: float = 0.001) -> None:
    api.client.post(
        "/api/v1/assets", json={"ticker": "WEGE3", "name": "WEG", "asset_type": "STOCK_BR"}
    )
    days = _weekdays(START, END)
    with api.uow_factory() as uow:
        uow.market_series.upsert_points(
            tr_symbol("WEGE3"),
            [(d, 40.0 * (1 + wege_drift) ** i) for i, d in enumerate(days)],
            unit=SeriesUnit.PRICE,
        )
        uow.market_series.upsert_points(
            index_symbol("IBOV"),
            [(d, 120_000.0 + 50 * i) for i, d in enumerate(days)],
            unit=SeriesUnit.INDEX_POINTS,
        )
        uow.market_series.upsert_points(
            "CDI", [(d, 0.04) for d in days], unit=SeriesUnit.PERCENT_PER_DAY
        )
        uow.commit()


# --- engine and pure helpers ----------------------------------------------------------------


def test_the_engine_stops_at_the_deadline() -> None:
    days = month_ends(START, END)
    history = MarketHistory({"A": PriceSeries.from_points([(d, 10.0) for d in days])})
    config = BacktestConfig(START, END, monthly_contribution=100.0, cash_symbol=None)
    asset = SimulatedAsset("A", "A", AssetType.STOCK_BR, ArcaClass.ACOES)
    with pytest.raises(SimulationTimeout):
        run_backtest([asset], history, InvestmentPolicy(), config, deadline=lambda: True)
    with pytest.raises(SimulationTimeout):
        run_benchmark("A", history, config, deadline=lambda: True)
    assert run_benchmark("A", history, config, deadline=lambda: False).points


def test_params_round_trip_and_hash() -> None:
    params = BacktestParams(START, END, 1000.0, rebalance=True, benchmarks=("CDI", "IFIX"))
    assert BacktestParams.from_dict(params.to_dict()) == params
    assert params_hash(params) == params_hash(BacktestParams.from_dict(params.to_dict()))
    assert params_hash(params) != params_hash(replace(params, monthly_contribution=1001.0))

    run = new_backtest_run(params, label="teste")
    assert run.status == SimulationStatus.PENDING
    assert run.code_version == ENGINE_VERSION and run.seed > 0
    # The label is not an input: the same parameters keep the same hash.
    assert run.params_hash == new_backtest_run(params, label="outro").params_hash


def test_data_hash_follows_every_input() -> None:
    days = month_ends(START, END)
    history = MarketHistory({"A": PriceSeries.from_points([(d, 10.0) for d in days])})
    changed = MarketHistory({"A": PriceSeries.from_points([(d, 10.5) for d in days])})
    asset = SimulatedAsset("A", "A", AssetType.STOCK_BR, ArcaClass.ACOES)
    policy = InvestmentPolicy()
    base = data_hash(history, [asset], policy, [], [])
    assert base == data_hash(history, [asset], policy, [], [])
    assert base != data_hash(changed, [asset], policy, [], [])
    assert base != data_hash(history, [replace(asset, arca_class=ArcaClass.CAIXA)], policy, [], [])


# --- persistence, worker and routes -----------------------------------------------------------


def test_submit_run_and_read_results(api: SimpleNamespace) -> None:
    _seed(api)
    response = api.client.post("/api/v1/simulations/backtests", json=REQUEST)
    assert response.status_code == 202
    queued = response.json()
    assert queued["status"] == "PENDING" and queued["data_hash"] is None

    counts = run_pending_simulations_job(api.uow_factory, timeout_seconds=60)
    assert counts == {"DONE": 1}

    detail = api.client.get(f"/api/v1/simulations/{queued['id']}").json()
    assert detail["status"] == "DONE"
    assert detail["data_hash"] and detail["code_version"] == ENGINE_VERSION
    assert detail["started_at"] and detail["finished_at"]
    keys = [r["key"] for r in detail["results"]]
    assert keys == ["strategy", "benchmark:CDI", "benchmark:IBOV"]
    strategy = detail["results"][0]
    assert len(strategy["points"]) == len(month_ends(START, END))
    assert strategy["summary"]["contributed"] == pytest.approx(6000.0)
    assert strategy["summary"]["final_value"] > 0
    assert "ACOES" in strategy["points"][-1]["by_class"]
    assert strategy["survivorship_bias"] is False

    listed = api.client.get("/api/v1/simulations").json()
    assert [r["id"] for r in listed] == [queued["id"]]
    assert run_pending_simulations_job(api.uow_factory, timeout_seconds=60) == {}


def test_same_inputs_reuse_the_stored_result(api: SimpleNamespace) -> None:
    _seed(api)
    first = api.client.post("/api/v1/simulations/backtests", json=REQUEST).json()
    second = api.client.post(
        "/api/v1/simulations/backtests", json={**REQUEST, "label": "de novo"}
    ).json()
    run_pending_simulations_job(api.uow_factory, timeout_seconds=60)

    a = api.client.get(f"/api/v1/simulations/{first['id']}").json()
    b = api.client.get(f"/api/v1/simulations/{second['id']}").json()
    assert a["reused_from"] is None and b["reused_from"] == first["id"]
    assert a["data_hash"] == b["data_hash"]
    assert a["results"] == b["results"]

    # New data changes the hash: the next run is computed again.
    with api.uow_factory() as uow:
        uow.market_series.upsert_points(
            tr_symbol("WEGE3"), [(date(2024, 6, 28), 99.0)], unit=SeriesUnit.PRICE
        )
        uow.commit()
    third = api.client.post("/api/v1/simulations/backtests", json=REQUEST).json()
    run_pending_simulations_job(api.uow_factory, timeout_seconds=60)
    c = api.client.get(f"/api/v1/simulations/{third['id']}").json()
    assert c["reused_from"] is None and c["data_hash"] != a["data_hash"]


def test_time_limit_and_failure_are_stored(api: SimpleNamespace) -> None:
    _seed(api)
    run_id = api.client.post("/api/v1/simulations/backtests", json=REQUEST).json()["id"]
    ticks = iter(range(0, 10_000, 100))
    final = execute_next_run(api.uow_factory, timeout_seconds=50, clock=lambda: next(ticks))
    assert final is not None and final.status == SimulationStatus.TIMEOUT
    assert "time limit" in (final.error or "")
    detail = api.client.get(f"/api/v1/simulations/{run_id}").json()
    assert detail["status"] == "TIMEOUT" and detail["results"] == []

    with api.uow_factory() as uow:
        broken = new_backtest_run(BacktestParams(START, END, 1000.0))
        uow.simulations.add(replace(broken, params={"start": "not a date"}))
        uow.commit()
    assert run_pending_simulations_job(api.uow_factory, timeout_seconds=60) == {"FAILED": 1}
    failed = api.client.get("/api/v1/simulations").json()[0]
    assert failed["status"] == "FAILED" and "ValueError" in failed["error"]


def test_request_validation(api: SimpleNamespace) -> None:
    post = api.client.post
    assert (
        post("/api/v1/simulations/backtests", json={**REQUEST, "end": "2023-01-01"}).status_code
        == 400
    )
    future = (date.today() + timedelta(days=30)).isoformat()
    assert post("/api/v1/simulations/backtests", json={**REQUEST, "end": future}).status_code == 400
    assert (
        post(
            "/api/v1/simulations/backtests", json={**REQUEST, "monthly_contribution": 0}
        ).status_code
        == 422
    )
    assert (
        post("/api/v1/simulations/backtests", json={**REQUEST, "benchmarks": ["XPTO"]}).status_code
        == 422
    )
    assert api.client.get("/api/v1/simulations/999").status_code == 404


def test_catalog_universe_is_recorded_and_flagged(api: SimpleNamespace) -> None:
    _seed(api)
    run = api.client.post(
        "/api/v1/simulations/backtests",
        json={**REQUEST, "universe": "REGISTERED_AND_CATALOG", "catalog_top": 7},
    ).json()
    assert run["params"]["catalog_top"] == 7
    plain = api.client.post(
        "/api/v1/simulations/backtests", json={**REQUEST, "catalog_top": 7}
    ).json()
    assert plain["params"]["catalog_top"] == 0  # only used with the catalog universe


def test_repository_replaces_results(api: SimpleNamespace) -> None:
    with api.uow_factory() as uow:
        run = uow.simulations.add(new_backtest_run(BacktestParams(START, END, 1.0)))
        item = SimulationResult(run_id=run.id, key="strategy", label="x", summary={"a": 1})  # type: ignore[arg-type]
        uow.simulations.save_results(run.id, [item, replace(item, key="benchmark:CDI")])  # type: ignore[arg-type]
        uow.simulations.save_results(run.id, [replace(item, label="y")])  # type: ignore[arg-type]
        uow.commit()
        stored = uow.simulations.results(run.id)  # type: ignore[arg-type]
    assert [(r.key, r.label) for r in stored] == [("strategy", "y")]


def test_cash_asset_takes_the_caixa_class(api: SimpleNamespace) -> None:
    _seed(api)
    api.client.post("/api/v1/simulations/backtests", json=REQUEST)
    run_pending_simulations_job(api.uow_factory, timeout_seconds=60)
    detail = api.client.get("/api/v1/simulations").json()[0]
    result = api.client.get(f"/api/v1/simulations/{detail['id']}").json()["results"][0]
    assert CASH_TICKER not in result["unavailable"]
    assert "CAIXA" in result["points"][-1]["by_class"]


def test_mcp_operations(api: SimpleNamespace) -> None:
    _seed(api)
    handlers = AgenticRuntimeHandlers(
        uow_factory=api.uow_factory,
        portfolio_service=PortfolioApplicationService(offline_gateway()),
    )
    submit = CATALOG_BY_NAME["simulation.backtest"]
    assert submit.kind == "command"
    run = submit.invoke(handlers, submit.input_model(**REQUEST))
    run_pending_simulations_job(api.uow_factory, timeout_seconds=60)

    get = CATALOG_BY_NAME["simulation.get"]
    detail = get.invoke(handlers, get.input_model(run_id=run.id))
    assert detail.status == SimulationStatus.DONE and detail.results
    listing = CATALOG_BY_NAME["simulation.list"]
    assert [r.id for r in listing.invoke(handlers, listing.input_model())] == [run.id]


def test_scheduler_polls_only_when_a_run_is_queued(api: SimpleNamespace) -> None:
    calls: list[int] = []
    tick = _when_pending(api.uow_factory, lambda: calls.append(1))
    tick()
    assert calls == []
    api.client.post("/api/v1/simulations/backtests", json=REQUEST)
    tick()
    assert calls == [1]
