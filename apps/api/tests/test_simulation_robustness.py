"""Phase 33.4: historical crises, synthetic shocks and counted rule variants."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from domain.agentic.services.catalog import CATALOG_BY_NAME, AgenticRuntimeHandlers
from domain.policy.services.policy import ArcaPolicy, ClassPolicy, InvestmentPolicy
from domain.portfolio.services.service import PortfolioApplicationService
from domain.shared.enums import ArcaClass, SeriesUnit
from domain.simulation.data import index_symbol, tr_symbol
from domain.simulation.engine import BacktestPoint, BacktestResult, _summary
from domain.simulation.entities import (
    SimulationKind,
    SimulationResult,
    SimulationRun,
    SimulationStatus,
)
from domain.simulation.market import month_ends
from domain.simulation.robustness import (
    SYNTHETIC_SHOCKS,
    apply_shock,
    distribution,
    holdout_start,
    rule_variants,
    sample_warnings,
    window_outcome,
    with_band,
)
from domain.simulation.runs import to_stored_result
from domain.simulation.services.use_cases import build_robustness
from tests.conftest import offline_gateway
from worker.jobs import run_pending_simulations_job

SHOCKS = {s.key: s for s in SYNTHETIC_SHOCKS}


def _points(days: list[date], monthly: float, contribution: float = 100.0) -> list[BacktestPoint]:
    """Constant monthly return with a contribution at every month-end."""
    out: list[BacktestPoint] = []
    value = contributed = 0.0
    for day in days:
        value = value * (1.0 + monthly) + contribution
        contributed += contribution
        out.append(
            BacktestPoint(
                day=day,
                contribution=contribution,
                contributed=contributed,
                market_value=value,
                cash=0.0,
                fees=0.0,
                by_class={ArcaClass.ACOES: value},
            )
        )
    return out


# --- windows ------------------------------------------------------------------------------


def test_window_return_removes_the_contributions() -> None:
    days = month_ends(date(2008, 1, 1), date(2009, 12, 31))
    outcome = window_outcome(_points(days, 0.01), date(2008, 9, 1), date(2009, 2, 28))
    # Sep/2008..Feb/2009 = 6 months of +1% each, whatever was contributed.
    assert outcome.covered and outcome.months == 6
    assert outcome.return_rate == pytest.approx(1.01**6 - 1, abs=1e-6)
    assert outcome.max_drawdown == 0.0


def test_window_drawdown_and_coverage() -> None:
    days = month_ends(date(2020, 1, 1), date(2020, 6, 30))
    values = [1000.0, 900.0, 720.0, 800.0, 800.0, 800.0]
    points = [
        BacktestPoint(d, 1000.0 if i == 0 else 0.0, 1000.0, v, 0.0, 0.0)
        for i, (d, v) in enumerate(zip(days, values, strict=True))
    ]
    covid = window_outcome(points, date(2020, 2, 1), date(2020, 3, 31))
    assert covid.return_rate == pytest.approx(-0.28)
    assert covid.max_drawdown == pytest.approx(-0.28)
    # The series must exist before the window and reach its last month.
    assert not window_outcome(points, date(2019, 12, 1), date(2020, 3, 31)).covered
    assert not window_outcome(points, date(2020, 5, 1), date(2020, 8, 31)).covered


def test_holdout_start_and_distribution() -> None:
    assert holdout_start(date(2024, 6, 28)) == date(2021, 7, 1)
    assert holdout_start(date(2024, 1, 31), months=1) == date(2024, 1, 1)
    assert holdout_start(date(2024, 1, 31), months=2) == date(2023, 12, 1)
    dist = distribution([0.1, None, 0.3, 0.2])
    assert (dist.count, dist.minimum, dist.median, dist.maximum) == (3, 0.1, 0.2, 0.3)
    assert distribution([None]).count == 0


# --- shocks and variants --------------------------------------------------------------------


def test_shocks_apply_first_order_moves() -> None:
    by_class = {ArcaClass.ACOES: 1000.0, ArcaClass.CAIXA: 500.0}
    equity = apply_shock(by_class, 100.0, SHOCKS["EQUITY_MINUS_30"])
    assert equity.before == 1600.0 and equity.after == 1300.0
    assert equity.change_rate == pytest.approx(-300 / 1600, abs=1e-6)
    assert equity.by_class[ArcaClass.CAIXA] == 600.0  # cash counts as CAIXA

    inflation = apply_shock(by_class, 0.0, SHOCKS["IPCA_12"])
    assert inflation.after == pytest.approx(1500.0 / 1.12, abs=0.01)
    assert apply_shock({}, 0.0, SHOCKS["FX_PLUS_40"]).change_rate == 0.0


def test_rule_variants_change_only_the_band() -> None:
    variants = rule_variants()
    assert len({v.key for v in variants}) == len(variants) == 8
    policy = InvestmentPolicy(
        arca=ArcaPolicy(
            {
                ArcaClass.ACOES: ClassPolicy(40.0, band_pct=5.0),
                ArcaClass.REAL_ESTATE: ClassPolicy(20.0),
                ArcaClass.CAIXA: ClassPolicy(30.0),
                ArcaClass.ATIVOS_INTERNACIONAIS: ClassPolicy(10.0),
            }
        )
    )
    wide = with_band(policy, 20.0)
    assert set(wide.arca.bands.values()) == {20.0}
    assert wide.arca.targets == policy.arca.targets


def test_sample_warnings() -> None:
    short = _points(month_ends(date(2024, 1, 1), date(2024, 12, 31)), 0.0)
    warnings = sample_warnings(short, {})  # type: ignore[arg-type]
    assert any("Amostra curta" in w for w in warnings)


def test_build_robustness_over_a_long_history() -> None:
    days = month_ends(date(2005, 1, 1), date(2024, 12, 31))
    run = SimulationRun(
        SimulationKind.BACKTEST, {}, "p", "v", 1, status=SimulationStatus.DONE, id=1
    )

    def stored(key: str, monthly: float) -> SimulationResult:
        pts = _points(days, monthly)
        return to_stored_result(1, key, BacktestResult(key, pts, _summary(pts, 0)))

    variant = rule_variants()[0].key
    results = [stored("strategy", 0.01), stored("benchmark:IBOV", 0.005), stored(variant, 0.008)]
    dto = build_robustness(run, results, trials_total=3)

    assert [s.key for s in dto.series] == ["strategy", "benchmark:IBOV"]
    gfc = next(c for c in dto.crises if c.key == "GFC_2008")
    assert gfc.outcomes["strategy"].covered
    assert gfc.outcomes["benchmark:IBOV"].return_rate == pytest.approx(1.005**6 - 1, abs=1e-6)
    assert len(dto.shocks) == len(SYNTHETIC_SHOCKS)
    assert dto.holdout_start == date(2022, 1, 1)
    only = dto.variants[0]
    assert only.selection.covered and only.holdout.covered
    assert only.holdout.months == 36
    assert dto.trials_in_run == 1 and dto.trials_total == 3
    assert dto.annual_twr_distribution.count == 1
    assert not any("Amostra curta" in w for w in dto.warnings)


# --- API, worker and MCP --------------------------------------------------------------------

START = date(2024, 1, 2)
END = date(2024, 6, 28)
REQUEST = {
    "start": START.isoformat(),
    "end": END.isoformat(),
    "monthly_contribution": 1000.0,
    "variants": True,
}


def _seed(api: SimpleNamespace) -> None:
    api.client.post(
        "/api/v1/assets", json={"ticker": "WEGE3", "name": "WEG", "asset_type": "STOCK_BR"}
    )
    days = [START + timedelta(days=i) for i in range((END - START).days + 1)]
    days = [d for d in days if d.weekday() < 5]
    with api.uow_factory() as uow:
        uow.market_series.upsert_points(
            tr_symbol("WEGE3"),
            [(d, 40.0 + 0.05 * i) for i, d in enumerate(days)],
            unit=SeriesUnit.PRICE,
        )
        uow.market_series.upsert_points(
            index_symbol("IBOV"),
            [(d, 120_000.0 + 10 * i) for i, d in enumerate(days)],
            unit=SeriesUnit.INDEX_POINTS,
        )
        uow.market_series.upsert_points(
            "CDI", [(d, 0.04) for d in days], unit=SeriesUnit.PERCENT_PER_DAY
        )
        uow.commit()


def test_variants_run_in_the_worker_and_are_counted(api: SimpleNamespace) -> None:
    _seed(api)
    run_id = api.client.post("/api/v1/simulations/backtests", json=REQUEST).json()["id"]
    run_pending_simulations_job(api.uow_factory, timeout_seconds=120)

    body = api.client.get(f"/api/v1/simulations/{run_id}/robustness").json()
    assert body["status"] == "DONE"
    assert body["trials_in_run"] == 8 and body["trials_total"] == 8
    assert body["annual_twr_distribution"]["count"] == 8
    assert {v["band_pct"] for v in body["variants"]} == {0.0, 5.0, 10.0, 20.0}
    assert [s["key"] for s in body["series"]] == ["strategy", "benchmark:CDI", "benchmark:IBOV"]
    assert len(body["shocks"]) == 5 and len(body["crises"]) == 5
    assert any("Amostra curta" in w for w in body["warnings"])
    assert any("Crises fora" in w for w in body["warnings"])

    # A reused run copies the results and is not a new trial.
    again = api.client.post("/api/v1/simulations/backtests", json=REQUEST).json()["id"]
    run_pending_simulations_job(api.uow_factory, timeout_seconds=120)
    assert api.client.get(f"/api/v1/simulations/{again}/robustness").json()["trials_total"] == 8

    plain = api.client.post(
        "/api/v1/simulations/backtests", json={**REQUEST, "variants": False}
    ).json()["id"]
    run_pending_simulations_job(api.uow_factory, timeout_seconds=120)
    assert api.client.get(f"/api/v1/simulations/{plain}/robustness").json()["variants"] == []
    assert api.client.get("/api/v1/simulations/999/robustness").status_code == 404

    op = CATALOG_BY_NAME["simulation.robustness"]
    handlers = AgenticRuntimeHandlers(
        uow_factory=api.uow_factory,
        portfolio_service=PortfolioApplicationService(offline_gateway()),
    )
    assert op.invoke(handlers, op.input_model(run_id=run_id)).trials_in_run == 8


def test_pending_run_has_an_empty_robustness(api: SimpleNamespace) -> None:
    run_id = api.client.post("/api/v1/simulations/backtests", json=REQUEST).json()["id"]
    body = api.client.get(f"/api/v1/simulations/{run_id}/robustness").json()
    assert body["status"] == "PENDING"
    assert body["variants"] == [] and body["shocks"] == [] and body["warnings"] == []
