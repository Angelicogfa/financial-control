"""Phase 42.3: valuation in the prior of α, with an out-of-sample gate."""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

import numpy as np
import pytest

from domain.disclosures.statements import (
    COMPANY,
    DIVIDENDS_PAID,
    EQUITY,
    NET_INCOME,
    SHARES,
    PitFundamentals,
)
from domain.forecast.model import forecast_asset
from domain.forecast.valuation_model import (
    CompanyInput,
    ValuationModel,
    add_months,
    company_yields,
    estimate,
    forward_alpha,
    split_factor_after,
    value_scores,
)
from domain.shared.enums import ArcaClass
from domain.simulation.candidates import FactorFit, ols_fit, shrink
from tests.conftest import offline_gateway
from worker.jobs import estimate_forecast_models_job

NOW = datetime(2026, 10, 30, 20, 0, tzinfo=UTC)


def _snap(delivered: date, ref: date, net_income: float, shares: float = 100.0) -> PitFundamentals:
    return PitFundamentals(
        cnpj="1",
        as_of=delivered,
        reference_date=ref,
        delivered_on=delivered,
        doc_type="DFP",
        version=1,
        template=COMPANY,
        values={NET_INCOME: net_income, EQUITY: 500.0, DIVIDENDS_PAID: 20.0, SHARES: shares},
    )


def test_split_factor_undoes_the_adjustment_after_the_statement() -> None:
    splits = [(date(2020, 5, 1), 2.0), (date(2023, 3, 1), 1.1)]
    assert split_factor_after(splits, date(2019, 12, 31)) == pytest.approx(2.2)
    assert split_factor_after(splits, date(2021, 12, 31)) == pytest.approx(1.1)
    assert split_factor_after(splits, date(2024, 1, 1)) == 1.0


def test_company_yields_use_only_delivered_and_recent_statements() -> None:
    company = CompanyInput(
        ticker="AAAA3",
        sector="X",
        snapshots=[_snap(date(2020, 3, 15), date(2019, 12, 31), 50.0)],
        # A 2:1 split in 2021: Yahoo halved the 2020 price, the real one was 10.
        prices={(2020, 2): 5.0, (2020, 4): 5.0, (2021, 6): 6.0},
        splits=[(date(2021, 1, 10), 2.0)],
    )
    yields = company_yields(company)
    assert (2020, 2) not in yields  # the statement was not delivered yet
    assert (2021, 6) not in yields  # 18 months old: too stale
    april = yields[(2020, 4)]
    assert april["earnings_yield"] == pytest.approx(50.0 / (10.0 * 100.0))
    assert april["book_yield"] == pytest.approx(500.0 / 1000.0)
    assert april["dividend_yield"] == pytest.approx(20.0 / 1000.0)
    assert "ebitda_ev" not in april  # no EBIT in this snapshot


def test_forward_alpha_needs_twelve_known_months() -> None:
    monthly = {add_months((2020, 1), i): 0.01 * (i % 2) for i in range(14)}
    forward = forward_alpha(monthly)
    assert set(forward) == {(2020, 1), (2020, 2)}
    assert forward[(2020, 1)] == pytest.approx(0.005)


def _panel(effect: float, seed: int = 7, companies: int = 30, months: int = 180):
    """Yields with persistent differences; α over the class follows them by `effect`."""
    rng = np.random.default_rng(seed)
    start = (2011, 1)
    yields, alphas, sectors = {}, {}, {}
    for c in range(companies):
        ticker = f"C{c:02d}"
        sectors[ticker] = "ABC"[c % 3]
        level = rng.normal(0.08, 0.02)
        value = level
        by_month, alpha = {}, {}
        for i in range(months):
            month = add_months(start, i)
            value = level + 0.85 * (value - level) + rng.normal(0, 0.01)
            by_month[month] = {"earnings_yield": value, "book_yield": value * 5}
        yields[ticker] = by_month
        yields_list = [by_month[add_months(start, i)]["earnings_yield"] for i in range(months)]
        for i in range(months):
            month = add_months(start, i)
            # Cheap now (relative to everyone): more return in the coming months.
            past = yields_list[i - 1] if i else yields_list[0]
            alpha[month] = effect * (past - 0.08) / 0.02 + rng.normal(0, 0.03)
        alphas[ticker] = alpha
    return yields, alphas, sectors


def test_the_gate_takes_a_real_effect() -> None:
    yields, alphas, sectors = _panel(effect=0.004)
    scores = value_scores(yields, sectors)
    model = estimate(
        scores, {t: forward_alpha(a) for t, a in alphas.items()}, sectors, as_of=date(2026, 1, 1)
    )
    assert model.passed, model.reason
    assert model.gamma > 0 and model.sign_probability > 0.9
    assert model.oos_improvement > 0 and len(model.origins) >= 5
    assert set(model.sectors) == {"A", "B", "C"}
    assert model.gamma_for("A") == model.sectors["A"]
    assert set(model.scores["C00"]) == {"z", "month"}
    assert ValuationModel.from_dict(model.to_dict()) == model


def test_the_gate_refuses_noise() -> None:
    yields, alphas, sectors = _panel(effect=0.0, seed=11)
    scores = value_scores(yields, sectors)
    model = estimate(
        scores, {t: forward_alpha(a) for t, a in alphas.items()}, sectors, as_of=date(2026, 1, 1)
    )
    assert not model.passed and model.gamma == 0.0
    assert model.gamma_for("A") == 0.0
    assert "não foi usado" in model.reason


def test_too_little_data_says_so() -> None:
    model = estimate({}, {}, {}, as_of=date(2026, 1, 1))
    assert not model.passed and model.months == 0 and "Poucos meses" in model.reason


def test_alpha_is_pulled_to_the_valuation_signal() -> None:
    rng = np.random.default_rng(1)
    x = rng.normal(0.0, 0.05, 40)
    y = x + rng.normal(0.0, 0.05, 40)
    a, a_se, b, b_se, resid = ols_fit(y, x)
    fit = FactorFit("X", ArcaClass.ACOES, 40, a, a_se, b, b_se, resid)
    plain = shrink(fit, 0.001)
    signalled = shrink(fit, 0.001, prior_mean=0.004)
    # shrinkage is rounded to 4 places
    assert signalled.alpha_post - plain.alpha_post == pytest.approx(
        signalled.shrinkage * 0.004, abs=1e-6
    )
    forecast = forecast_asset(
        signalled,
        np.full((200, 24), 0.0),
        cdi_monthly=0.008,
        price_now=10.0,
        drag_monthly=0.0,
        as_of=date(2026, 1, 1),
        seed=1,
        valuation_note="z de valuation +2.0",
    )
    driver = next(d for d in forecast.drivers if d.key == "VALUATION")
    assert driver.annual == pytest.approx((1 + signalled.shrinkage * 0.004) ** 12 - 1, abs=1e-4)
    assert driver.note == "z de valuation +2.0"


def test_estimation_job_without_statements_stores_nothing(api: SimpleNamespace) -> None:
    assert estimate_forecast_models_job(api.uow_factory, offline_gateway(), now=NOW) == {
        "companies": 0
    }
    quality = api.client.get("/api/v1/market/forecast-quality").json()
    assert quality["valuation"] is None


def test_quality_reports_the_valuation_model(api: SimpleNamespace) -> None:
    yields, alphas, sectors = _panel(effect=0.004)
    model = estimate(
        value_scores(yields, sectors),
        {t: forward_alpha(a) for t, a in alphas.items()},
        sectors,
        as_of=date(2026, 10, 30),
    )
    with api.uow_factory() as uow:
        uow.forecasts.save_model("VALUATION", date(2026, 10, 30), model.to_dict())
        uow.commit()
    data = api.client.get("/api/v1/market/forecast-quality").json()["valuation"]
    assert data["passed"] and data["gamma_used_annual_per_z"] > 0
    assert data["companies"] == 30 and len(data["origins"]) >= 5


def test_estimation_job_reads_the_stored_statements(api: SimpleNamespace) -> None:
    from domain.disclosures.entities import IssuerTicker
    from domain.disclosures.statements import DFP, StatementFact
    from tests.test_forecast import _seed
    from worker.jobs import refresh_asset_forecasts_job

    ids = _seed(api)
    cnpj = "84429695000111"
    facts = []
    for year in range(2017, 2026):
        ref, delivered = date(year, 12, 31), date(year + 1, 2, 20)
        for metric, value, start in (
            (NET_INCOME, 1e9 * (1 + 0.1 * (year % 3)), date(year, 1, 1)),
            (EQUITY, 8e9, None),
            (SHARES, 4.2e9, None),
        ):
            facts.append(
                StatementFact(
                    cnpj, DFP, ref, 1, delivered, "CON", COMPANY, metric, start, ref, value
                )
            )
    with api.uow_factory() as uow:
        uow.cvm_issuers.replace_all([IssuerTicker("WEGE3", cnpj, "WEG")])
        uow.cvm_statements.add_many(facts)
        uow.commit()

    details = estimate_forecast_models_job(api.uow_factory, offline_gateway(), now=NOW)
    assert details["companies"] == 1 and details["passed"] is False
    with api.uow_factory() as uow:
        stored = uow.forecasts.latest_model("VALUATION")
    model = ValuationModel.from_dict(stored.payload)
    assert "WEGE3" in model.scores  # time z: enough months of its own history

    refresh_asset_forecasts_job(api.uow_factory, offline_gateway(), now=NOW)
    with api.uow_factory() as uow:
        payload = uow.forecasts.latest("WEGE3").payload
    driver = next(d for d in payload["drivers"] if d["key"] == "VALUATION")
    assert driver["annual"] is None and driver["note"].startswith("z de valuation")
    assert ids["WEGE3"]
