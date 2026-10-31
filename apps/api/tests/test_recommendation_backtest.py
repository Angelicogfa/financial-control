"""Phase 45.6: the hierarchy tested in the past and the scoreboard of its runs."""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

import numpy as np
import pytest

from domain.agentic.services.catalog import CATALOG_BY_NAME, AgenticRuntimeHandlers
from domain.portfolio.services.service import PortfolioApplicationService
from domain.recommendation.ahp import DEFAULT_MATRICES, priority
from domain.recommendation.backtest import (
    Backtest,
    RunPortfolios,
    _eligible,
    add_months,
    backtest_weights,
    run_backtest,
    scoreboard,
)
from domain.recommendation.keys import CERRADO, MIXED, PROJECTION
from domain.recommendation.params import ConstructionParams
from tests.conftest import offline_gateway
from tests.test_mining_signals import seed_panel
from worker.jobs import backtest_recommendation_job, refresh_asset_lenses_job, run_mining_job

TODAY = date(2026, 10, 31)
NOW = datetime(2026, 10, 31, 22, 0, tzinfo=UTC)
WEIGHTS = priority(DEFAULT_MATRICES[MIXED]).weights


def _synthetic(effect: float, seed: int, companies: int = 30, months: int = 96):
    """A panel where QUALITY predicts next month's return over the class by `effect` per z."""
    rng = np.random.default_rng(seed)
    start = (2017, 1)
    stamps = [add_months(start, i) for i in range(months)]
    panel: dict = {}
    alphas: dict = {f"T{c:02d}": {} for c in range(companies)}
    returns: dict = {f"T{c:02d}": {} for c in range(companies)}
    for i, month in enumerate(stamps):
        panel[month] = {}
        for c in range(companies):
            ticker = f"T{c:02d}"
            z = float(rng.normal())
            panel[month][ticker] = {"QUALITY": z, "VALUE": float(rng.normal())}
            if i + 1 < months:
                nxt = stamps[i + 1]
                alpha = effect * z + float(rng.normal(0.0, 0.03))
                alphas[ticker][nxt] = alpha
                returns[ticker][nxt] = alpha + float(rng.normal(0.0, 0.01))
    for ticker in returns:  # the history the covariance needs before the first month
        for k in range(1, 37):
            returns[ticker][add_months(start, -k)] = float(rng.normal(0.0, 0.05))
    sectors = {f"T{c:02d}": f"Setor {c % 8}" for c in range(companies)}
    first = {t: add_months(start, -36) for t in returns}
    return panel, alphas, returns, sectors, first


def test_weights_leave_out_the_lenses_without_past() -> None:
    used = backtest_weights(WEIGHTS)
    assert CERRADO not in used and PROJECTION not in used
    assert sum(used.values()) == pytest.approx(1.0)


def test_gates_of_the_past() -> None:
    month = (2020, 6)
    first = {"OLD3": (2015, 1), "NEW3": (2020, 1), "RJ3": (2015, 1)}
    restructuring = {"RJ3": [(2019, 3)]}
    assert _eligible(["OLD3", "NEW3", "RJ3"], month, first, restructuring) == ["OLD3"]
    assert _eligible(["RJ3"], (2021, 6), first, restructuring) == ["RJ3"]  # 27 months later


def test_a_predictive_signal_passes_and_the_report_has_years() -> None:
    panel, alphas, returns, sectors, first = _synthetic(effect=0.01, seed=1)
    found = run_backtest(
        as_of=TODAY,
        panel=panel,
        alphas=alphas,
        returns=returns,
        sectors=sectors,
        first_month=first,
        restructuring={},
        weights=WEIGHTS,
        params=ConstructionParams(),
        scale_annual=0.06,
    )
    assert found.status == "OK" and found.passed
    assert found.difference_annual > 0 and found.probability >= 0.9
    assert found.months >= 60 and found.rebalances >= 20 and found.average_k >= 3
    assert "superou os pesos iguais" in found.reason
    assert [y.year for y in found.years][0] == 2017
    assert any("Cerrado manual" in n for n in found.notes)
    assert Backtest.from_dict(found.to_dict()) == found


def test_noise_does_not_pass_and_short_histories_say_so() -> None:
    panel, alphas, returns, sectors, first = _synthetic(effect=0.0, seed=2)
    noise = run_backtest(
        as_of=TODAY,
        panel=panel,
        alphas=alphas,
        returns=returns,
        sectors=sectors,
        first_month=first,
        restructuring={},
        weights=WEIGHTS,
        params=ConstructionParams(),
        scale_annual=0.06,
    )
    assert abs(noise.difference_annual) < 0.05
    short = {m: rows for m, rows in panel.items() if m < (2019, 1)}
    brief = run_backtest(
        as_of=TODAY,
        panel=short,
        alphas=alphas,
        returns=returns,
        sectors=sectors,
        first_month=first,
        restructuring={},
        weights=WEIGHTS,
        params=ConstructionParams(),
        scale_annual=0.06,
    )
    assert not brief.passed and "são precisos 5" in brief.reason
    empty = run_backtest(
        as_of=TODAY,
        panel={},
        alphas={},
        returns={},
        sectors={},
        first_month={},
        restructuring={},
        weights=WEIGHTS,
        params=ConstructionParams(),
        scale_annual=0.06,
    )
    assert empty.status == "INSUFFICIENT" and not empty.passed


def test_scoreboard_measures_the_runs_against_the_references() -> None:
    returns = {
        "GOOD3": {(2026, m): 0.03 for m in range(2, 11)},
        "BAD3": {(2026, m): -0.01 for m in range(2, 11)},
        "MID3": {(2026, m): 0.01 for m in range(2, 11)},
    }
    runs = [
        RunPortfolios(
            date(2026, 1, 9),
            recommended={"GOOD3": 1.0},
            eligible=["GOOD3", "BAD3", "MID3"],
            cerrado={"BAD3": 8.0, "MID3": 2.0},
        ),
        RunPortfolios(date(2026, 9, 5), recommended={"GOOD3": 1.0}, eligible=["GOOD3"], cerrado={}),
    ]
    lines = {line.horizon: line for line in scoreboard(runs, returns, (2026, 10))}
    assert set(lines) == {1, 3, 6}  # 12 months have not passed for any run
    one = lines[1]
    assert one.runs == 2 and one.cerrado_runs == 1
    assert one.vs_equal > 0 and one.beat_equal == 0.5  # the second run's only asset is itself
    assert one.vs_cerrado == pytest.approx(0.03 - (0.8 * -0.01 + 0.2 * 0.01))
    assert lines[6].runs == 1


def test_backtest_job_api_and_mcp(api: SimpleNamespace) -> None:
    assert api.client.get("/api/v1/recommendation/backtest").json()["status"] == "NOT_COMPUTED"
    seed_panel(api)
    run_mining_job(api.uow_factory, offline_gateway(), now=NOW)
    refresh_asset_lenses_job(api.uow_factory, offline_gateway(), now=NOW)
    result = backtest_recommendation_job(api.uow_factory, offline_gateway(), now=NOW)
    # Twelve companies are fewer than the 20 a month needs: the test says so, it does not guess.
    assert result["status"] == "INSUFFICIENT" and not result["passed"]
    data = api.client.get("/api/v1/recommendation/backtest").json()
    assert data["status"] == "INSUFFICIENT" and "20 empresas" in data["reason"]
    assert data["scoreboard"] == []  # the only run is from this month
    handlers = AgenticRuntimeHandlers(
        uow_factory=api.uow_factory,
        portfolio_service=PortfolioApplicationService(offline_gateway()),
    )
    op = CATALOG_BY_NAME["recommendation.backtest"]
    assert op.kind == "query"
    assert op.invoke(handlers, op.input_model()).status == "INSUFFICIENT"
