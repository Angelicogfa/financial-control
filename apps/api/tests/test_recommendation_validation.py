"""Phase 45.7: the lens weights validated by the data, behind an out-of-sample gate."""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from domain.agentic.services.catalog import CATALOG_BY_NAME, AgenticRuntimeHandlers
from domain.forecast.valuation_model import forward_alpha
from domain.portfolio.services.service import PortfolioApplicationService
from domain.recommendation.ahp import DEFAULT_MATRICES, priority
from domain.recommendation.keys import CERRADO, DIVIDENDS, MIXED, PROJECTION, QUALITY, VALUATION
from domain.recommendation.validation import (
    LENS_WEIGHTS,
    LensWeights,
    candidate_weights,
    validate_lens_weights,
)
from tests.conftest import offline_gateway
from tests.test_mining_signals import seed_panel
from tests.test_recommendation_backtest import _synthetic
from worker.jobs import backtest_recommendation_job, refresh_asset_lenses_job, run_mining_job

TODAY = date(2026, 11, 1)
NOW = datetime(2026, 11, 1, 22, 0, tzinfo=UTC)
DECLARED = priority(DEFAULT_MATRICES[MIXED]).weights


def _by_ticker(panel: dict) -> dict:
    out: dict = {}
    for month, rows in panel.items():
        for ticker, values in rows.items():
            out.setdefault(ticker, {})[month] = values
    return out


def _validate(effect: float, seed: int, objective: str = MIXED) -> LensWeights:
    panel, alphas, _returns, _sectors, _first = _synthetic(effect=effect, seed=seed, months=120)
    return validate_lens_weights(
        as_of=TODAY,
        objective=objective,
        declared=DECLARED,
        panel=_by_ticker(panel),
        alphas=alphas,
        forward={t: forward_alpha(a) for t, a in alphas.items()},
    )


def test_the_candidate_is_half_declared_half_data() -> None:
    class Est:
        def __init__(self, estimate: float, sign: float) -> None:
            self.estimate, self.sign_probability = estimate, sign

    estimates = {
        "QUALITY": Est(0.002, 0.99),
        "VALUE": Est(0.001, 0.95),
        "IMPROVEMENT": Est(-0.002, 0.99),  # hurts: 0
        "MOMENTUM": Est(0.003, 0.6),  # sign not clear: 0
        "INCOME": Est(0.0, 0.5),
        "RISK": Est(0.0, 0.5),
    }
    data, candidate = candidate_weights(DECLARED, estimates)
    share = 1 - DECLARED[CERRADO] - DECLARED[PROJECTION]
    assert data[QUALITY] == pytest.approx(share * 2 / 3, abs=1e-5) and data[
        VALUATION
    ] == pytest.approx(share / 3, abs=1e-5)
    assert candidate[CERRADO] == DECLARED[CERRADO] and candidate[PROJECTION] == DECLARED[PROJECTION]
    assert candidate[QUALITY] == pytest.approx((DECLARED[QUALITY] + data[QUALITY]) / 2)
    assert sum(candidate.values()) == pytest.approx(1.0, abs=1e-5)
    nothing = {k: Est(0.0, 0.5) for k in estimates}
    assert candidate_weights(DECLARED, nothing) == ({}, dict(DECLARED))


def test_a_predictive_lens_moves_the_weights_and_noise_does_not() -> None:
    found = _validate(effect=0.02, seed=1)
    assert found.passed and found.probability >= 0.9 and found.origins >= 5
    assert found.used[QUALITY] > DECLARED[QUALITY]
    assert sum(found.used.values()) == pytest.approx(1.0)
    quality = next(line for line in found.lines if line.lens == QUALITY)
    assert quality.sign_probability > 0.9 and quality.used == found.used[QUALITY]
    assert LensWeights.from_dict(found.to_dict()) == found

    noise = _validate(effect=0.0, seed=2)
    assert not noise.passed and noise.used == pytest.approx(DECLARED)

    dividends = _validate(effect=0.02, seed=1, objective=DIVIDENDS)
    assert not dividends.passed and "Dividendos" in dividends.reason


def test_the_job_stores_the_weights_and_the_api_and_mcp_read_them(api: SimpleNamespace) -> None:
    assert api.client.get("/api/v1/recommendation/weights").json()["status"] == "NOT_COMPUTED"
    seed_panel(api)
    run_mining_job(api.uow_factory, offline_gateway(), now=NOW)
    refresh_asset_lenses_job(api.uow_factory, offline_gateway(), now=NOW)
    result = backtest_recommendation_job(api.uow_factory, offline_gateway(), now=NOW)
    assert result["weights_validated"] is False  # twelve synthetic companies are too few
    data = api.client.get("/api/v1/recommendation/weights").json()
    assert data["status"] == "OK" and data["objective"] == MIXED and len(data["lines"]) == 6
    matrix = api.client.get("/api/v1/recommendation/matrix").json()["classes"][0]
    assert matrix["weights_source"] == "AHP"
    handlers = AgenticRuntimeHandlers(
        uow_factory=api.uow_factory,
        portfolio_service=PortfolioApplicationService(offline_gateway()),
    )
    op = CATALOG_BY_NAME["recommendation.weights"]
    assert op.invoke(handlers, op.input_model()).status == "OK"


def test_the_lens_run_uses_validated_weights(api: SimpleNamespace) -> None:
    seed_panel(api)
    run_mining_job(api.uow_factory, offline_gateway(), now=NOW)
    validated = _validate(effect=0.02, seed=1)
    assert validated.passed
    with api.uow_factory() as uow:
        uow.forecasts.save_model(LENS_WEIGHTS, TODAY, validated.to_dict())
        uow.commit()
    refresh_asset_lenses_job(api.uow_factory, offline_gateway(), now=NOW)
    matrix = api.client.get("/api/v1/recommendation/matrix").json()["classes"][0]
    assert matrix["weights_source"] == "VALIDATED"
    used = {w["lens"]: w["weight"] for w in matrix["weights"]}
    assert used[QUALITY] == pytest.approx(validated.used[QUALITY], abs=1e-5)
