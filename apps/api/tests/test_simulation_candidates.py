"""Phase 33.7: candidate assets (layer D) against their class, shrunk, on the layer B paths."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from domain.agentic.services.catalog import CATALOG_BY_NAME, AgenticRuntimeHandlers
from domain.policy.services.policy import ArcaPolicy, ClassPolicy, InvestmentPolicy
from domain.portfolio.services.service import PortfolioApplicationService
from domain.shared.enums import ArcaClass, AssetType, SeriesUnit
from domain.simulation.candidate_runs import CandidateOption, select_candidates
from domain.simulation.candidates import (
    DEFAULT_ALPHA_SD_MONTHLY,
    FactorFit,
    candidate_excess,
    class_tau,
    ols_fit,
    p_improvement,
    ranking_stability,
    rupture_zone,
    shrink,
)
from domain.simulation.data import index_symbol, tr_symbol
from tests.conftest import offline_gateway
from worker.jobs import run_pending_simulations_job

A, CX = ArcaClass.ACOES, ArcaClass.CAIXA


def _fit(alpha: float, months: int, noise: float, seed: int = 1) -> FactorFit:
    rng = np.random.default_rng(seed)
    x = rng.normal(0.0, 0.05, months)
    y = alpha + 1.0 * x + rng.normal(0.0, noise, months)
    a, a_se, b, b_se, resid = ols_fit(y, x)
    return FactorFit("X", A, months, a, a_se, b, b_se, resid)


# --- factor model and shrinkage (design 8.2) --------------------------------------------------


def test_ols_recovers_a_known_alpha_and_beta() -> None:
    rng = np.random.default_rng(2)
    x = rng.normal(0.0, 0.05, 5000)
    y = 0.002 + 1.3 * x + rng.normal(0.0, 0.01, 5000)
    a, a_se, b, b_se, resid = ols_fit(y, x)
    assert a == pytest.approx(0.002, abs=4 * a_se) and b == pytest.approx(1.3, abs=4 * b_se)
    assert resid.std() == pytest.approx(0.01, rel=0.05)


def test_a_long_history_keeps_its_alpha_and_a_short_one_is_shrunk() -> None:
    tau = 0.004  # true alphas of the class spread about 5% a year
    long_fit = shrink(_fit(0.02, 600, 0.03), tau)
    short_fit = shrink(_fit(0.02, 36, 0.08), tau)
    assert long_fit.alpha_post > 0.8 * long_fit.alpha
    assert long_fit.shrinkage < 0.15
    assert short_fit.shrinkage > 0.7
    assert abs(short_fit.alpha_post) < abs(short_fit.alpha) * 0.3
    # β is pulled to 1 more when it is estimated with few data.
    assert abs(short_fit.beta_post - 1.0) <= abs(short_fit.beta - 1.0)


def test_class_tau_by_empirical_bayes() -> None:
    noise_only = [_fit(0.0, 60, 0.05, seed=s) for s in range(30)]
    assert class_tau(noise_only) < 0.003  # spread explained by noise alone
    real = [_fit(a, 240, 0.02, seed=s) for s, a in enumerate(np.linspace(-0.02, 0.02, 30))]
    assert class_tau(real) == pytest.approx(np.std(np.linspace(-0.02, 0.02, 30), ddof=1), rel=0.3)
    assert class_tau(noise_only[:2]) == DEFAULT_ALPHA_SD_MONTHLY


def test_candidate_paths_follow_the_class_and_the_rupture() -> None:
    fit = shrink(_fit(0.0, 120, 0.0001), 0.0)
    class_excess = np.full((200, 24), 0.01)
    calm = candidate_excess(
        fit,
        class_excess,
        rupture_annual=0.0,
        rupture_loss=0.55,
        mean_block=12.0,
        rng=np.random.default_rng(1),
    )
    assert calm.mean() == pytest.approx(0.01 * fit.beta_post, abs=0.003)
    broken = candidate_excess(
        fit,
        class_excess,
        rupture_annual=1.0,
        rupture_loss=0.55,
        mean_block=12.0,
        rng=np.random.default_rng(1),
    )
    assert (broken < -0.5).mean() > 0.05  # every month a ~6% chance of the 55% loss


def test_ranking_stability_and_p_improvement() -> None:
    rng = np.random.default_rng(3)
    clear = np.vstack([rng.normal(10.0, 1.0, 500), *(rng.normal(0.0, 1.0, 500) for _ in range(9))])
    stability = ranking_stability(clear, resamples=50, rng=rng, top_k=1)
    assert stability[0] == 1.0 and stability[1:].sum() == 0.0
    noise = np.vstack([rng.normal(0.0, 1.0, 500) for _ in range(10)])
    unstable = ranking_stability(noise, resamples=50, rng=rng, top_k=1)
    assert unstable.max() < 0.9  # no noise candidate wins every resample
    p, low, high = p_improvement(rng.normal(0.0, 1.0, 2000))
    assert low < 0.5 < high and p == pytest.approx(0.5, abs=0.05)


def test_rupture_zones() -> None:
    assert rupture_zone(AssetType.FII) == "FII"
    assert rupture_zone(AssetType.ETF_BR) == "ETF"
    assert rupture_zone(AssetType.STOCK_BR) == "NO_DATA"
    assert rupture_zone(AssetType.STOCK_BR, "STRESS") == "STRESS"


def test_select_candidates_applies_the_real_contribution_filters() -> None:
    def option(ticker: str, source: str = "WATCHLIST", **kw: object) -> CandidateOption:
        base = {
            "name": ticker,
            "arca_class": A,
            "asset_type": AssetType.STOCK_BR,
            "eligible": True,
            "valuation_verdict": None,
            "dividend_yield": 0.05,
            "suspicious": False,
        }
        base.update(kw)
        return CandidateOption(ticker=ticker, source=source, **base)  # type: ignore[arg-type]

    options = [
        option("SCR2", "SCREENER", eligible=None, volume_brl=1e6),
        option("SCR1", "SCREENER", eligible=None, volume_brl=9e6),
        option("BAD3", suspicious=True),
        option("NOPE3", eligible=False),
        option("HELD3"),
        option("WEGE3"),
    ]
    chosen, excluded = select_candidates(options, held={"HELD3"}, limit=2)
    assert [c.ticker for c in chosen] == ["WEGE3", "SCR1"]
    reasons = {e["ticker"]: e["reason"] for e in excluded}
    assert reasons["BAD3"].startswith("Dado suspeito")
    assert reasons["NOPE3"].startswith("Fora dos critérios")
    assert reasons["SCR2"].startswith("Além do teto")
    assert "HELD3" not in reasons
    loose, _ = select_candidates(
        options, held=set(), include_ineligible=True, include_suspicious=True
    )
    assert {"BAD3", "NOPE3", "HELD3"} <= {c.ticker for c in loose}


# --- worker, routes and MCP --------------------------------------------------------------------

TODAY = date.today()
REQUEST = {
    "horizon_years": 3,
    "monthly_contribution": 1000.0,
    "initial_by_class": {"ACOES": 10_000.0, "CAIXA": 5000.0},
    "cdi_rate": 0.10,
    "ipca_rate": 0.04,
    "wealth_goal": 30_000.0,
    "paths": 300,
    "include_screener": False,
    "include_ineligible": True,
}


def _weekdays(years: int) -> list[date]:
    days, day = [], TODAY - timedelta(days=years * 365)
    while day <= TODAY:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def _seed(api: SimpleNamespace) -> None:
    days = _weekdays(9)
    rng = np.random.default_rng(4)
    ibov_returns = rng.normal(0.0004, 0.012, len(days))
    ibov = 100_000.0 * np.cumprod(1.0 + ibov_returns)
    wege = 40.0 * np.cumprod(1.0 + 0.0002 + 1.1 * ibov_returns + rng.normal(0.0, 0.008, len(days)))
    short_days = days[-300:]  # about 14 months: below the 36-month minimum
    newb = 10.0 * np.cumprod(1.0 + rng.normal(0.001, 0.02, len(short_days)))
    for ticker in ("WEGE3", "NEWB3"):
        api.client.post(
            "/api/v1/assets", json={"ticker": ticker, "name": ticker, "asset_type": "STOCK_BR"}
        )
    targets = {A: 60.0, CX: 40.0}
    with api.uow_factory() as uow:
        uow.market_series.upsert_points(
            index_symbol("IBOV"), list(zip(days, ibov, strict=True)), unit=SeriesUnit.INDEX_POINTS
        )
        uow.market_series.upsert_points(
            "CDI", [(d, 0.04) for d in days], unit=SeriesUnit.PERCENT_PER_DAY
        )
        uow.market_series.upsert_points(
            tr_symbol("WEGE3"), list(zip(days, wege, strict=True)), unit=SeriesUnit.PRICE
        )
        uow.market_series.upsert_points(
            tr_symbol("NEWB3"), list(zip(short_days, newb, strict=True)), unit=SeriesUnit.PRICE
        )
        uow.policies.add(
            InvestmentPolicy(
                arca=ArcaPolicy({c: ClassPolicy(target_pct=targets.get(c, 0.0)) for c in ArcaClass})
            )
        )
        uow.commit()


def test_candidates_run_in_the_worker(api: SimpleNamespace) -> None:
    _seed(api)
    response = api.client.post("/api/v1/simulations/candidates", json=REQUEST)
    assert response.status_code == 202
    queued = response.json()
    assert queued["kind"] == "CANDIDATES"
    assert {c["ticker"] for c in queued["params"]["candidates"]} == {"WEGE3", "NEWB3"}

    assert run_pending_simulations_job(api.uow_factory, timeout_seconds=120) == {"DONE": 1}
    data = api.client.get(f"/api/v1/simulations/{queued['id']}/candidates").json()
    assert data["status"] == "DONE" and data["tested"] == 2 and data["evaluated"] == 1
    assert data["excluded"] == [
        {"ticker": "NEWB3", "reason": "Menos de 36 meses de histórico guardado"}
    ]
    candidate = data["candidates"][0]
    assert candidate["ticker"] == "WEGE3" and candidate["source"] == "WATCHLIST"
    fit, effect = candidate["fit"], candidate["effect"]
    assert fit["months"] >= 36 and fit["beta"] == pytest.approx(1.1, abs=0.3)
    assert 0.0 <= effect["p_improve_low"] <= effect["p_improve"] <= effect["p_improve_high"] <= 1.0
    assert effect["rank"] == 1 and effect["top_k_share"] == 1.0
    assert effect["share_in_class"] == pytest.approx(1.0)  # no stock held: its class alone
    assert effect["delta_goal_probability"] is not None
    assert data["base"]["goal_probability"] is not None
    assert any("não recomendação" in w for w in data["warnings"])
    assert api.client.get(f"/api/v1/simulations/{queued['id']}/robustness").status_code == 400


def test_candidates_need_somebody_to_evaluate(api: SimpleNamespace) -> None:
    # No watchlist and no screener: nothing to evaluate.
    response = api.client.post("/api/v1/simulations/candidates", json=REQUEST)
    assert response.status_code == 400 and response.json()["code"] == "NO_CANDIDATES"


def test_candidates_mcp(api: SimpleNamespace) -> None:
    _seed(api)
    handlers = AgenticRuntimeHandlers(
        uow_factory=api.uow_factory,
        portfolio_service=PortfolioApplicationService(offline_gateway()),
    )
    submit = CATALOG_BY_NAME["simulation.find_candidates"]
    assert submit.kind == "command"
    run = submit.invoke(handlers, submit.input_model(**REQUEST))
    run_pending_simulations_job(api.uow_factory, timeout_seconds=120)
    read = CATALOG_BY_NAME["simulation.candidates"]
    data = read.invoke(handlers, read.input_model(run_id=run.id))
    assert [c.ticker for c in data.candidates] == ["WEGE3"]
