"""Phases 43.3-43.5: weights and gates, findings and record of the Garimpo."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import numpy as np
import pytest

from domain.agentic.services.catalog import CATALOG_BY_NAME, AgenticRuntimeHandlers
from domain.disclosures.entities import IssuerTicker
from domain.forecast.valuation_model import add_months, forward_alpha, month_end
from domain.mining.findings import last_month, reason, record, run_findings
from domain.mining.model import FINDINGS, MiningModel, estimate_mining_model
from domain.mining.repositories import MiningFinding, MiningSignal
from domain.mining.runs import MINING
from domain.mining.signals import IMPROVEMENT, MOMENTUM, QUALITY, VALUE
from domain.portfolio.services.service import PortfolioApplicationService
from domain.shared.entities import CatalogInstrument
from domain.shared.enums import AssetType
from tests.conftest import offline_gateway

START = (2012, 1)


def _panel(effect: float, seed: int, companies: int = 30, months: int = 150):
    """VALUE and QUALITY persist; the next months' return over the class follows VALUE."""
    rng = np.random.default_rng(seed)
    signals, alphas = {}, {}
    for c in range(companies):
        ticker = f"C{c:02d}3"
        value = rng.normal()
        quality = rng.normal()
        by_month, alpha = {}, {}
        for i in range(months):
            month = add_months(START, i)
            value = 0.9 * value + rng.normal(0, 0.45)
            quality = 0.95 * quality + rng.normal(0, 0.3)
            by_month[month] = {
                VALUE: float(np.clip(value, -3, 3)),
                QUALITY: float(np.clip(quality, -3, 3)),
                MOMENTUM: float(rng.normal()),
            }
            previous = by_month.get(add_months(month, -1), by_month[month])
            alpha[month] = effect * previous[VALUE] + rng.normal(0, 0.03)
        signals[ticker] = by_month
        alphas[ticker] = alpha
    forward = {t: forward_alpha(a) for t, a in alphas.items()}
    return signals, alphas, forward


@pytest.fixture(scope="module")
def real():
    signals, alphas, forward = _panel(effect=0.006, seed=5)
    return (
        signals,
        alphas,
        forward,
        estimate_mining_model(signals, forward, as_of=date(2026, 10, 30)),
    )


def test_a_real_signal_passes_the_gate(real) -> None:
    _signals, _alphas, _forward, model = real
    assert model.passed, model.reason
    assert model.weights[VALUE] > 0
    assert model.oos_excess_annual > 0 and model.oos_probability >= 0.9
    assert model.pbo is not None and model.loss_probability <= 0.25
    assert model.variants == 15 * 3
    assert MiningModel.from_dict(model.to_dict()) == model


def test_noise_does_not_pass() -> None:
    signals, _alphas, forward = _panel(effect=0.0, seed=9)
    model = estimate_mining_model(signals, forward, as_of=date(2026, 10, 30))
    assert not model.passed
    assert "não basta" in model.reason or "sorte" in model.reason or "anos" in model.reason


def test_findings_are_the_best_scores_with_a_reason(real) -> None:
    signals, _alphas, _forward, model = real
    month = last_month(signals)
    assert month == add_months(START, 149)
    found = run_findings(signals, model, date(2026, 10, 30))
    assert [f.rank for f in found] == list(range(1, FINDINGS + 1))
    assert all(f.trusted for f in found)
    values = [signals[f.ticker][month][VALUE] for f in found]
    assert np.mean(values) > np.mean([s[month][VALUE] for s in signals.values()])
    assert found[0].reason.startswith("Barata frente ao próprio histórico")


def test_reason_in_words() -> None:
    assert reason({VALUE: 1.8, QUALITY: -0.5}, {VALUE: 0.004, QUALITY: 0.002}) == (
        "Barata frente ao próprio histórico e ao setor (z +1,8)"
    )
    assert reason({IMPROVEMENT: -1.0}, {IMPROVEMENT: -0.001}) == "Resultados piorando (z -1,0)"
    assert reason({VALUE: 0.5}, {VALUE: 0.0}) == "Sem sinal que se destaque."


def test_record_counts_who_beat_the_universe(real) -> None:
    signals, alphas, _forward, model = real
    month = add_months(START, 100)
    findings = [
        MiningFinding(date(2020, 5, 1), month_end(month), rank, t, 0.01, True, {}, "")
        for rank, t in enumerate(sorted(signals, key=lambda t: -signals[t][month][VALUE])[:10], 1)
    ]
    lines = record(findings, alphas)
    twelve = next(line for line in lines if line.horizon == 12 and line.trusted)
    assert twelve.runs == 1 and twelve.findings == 10
    assert twelve.beat_low <= twelve.beat_share <= twelve.beat_high
    assert twelve.mean_excess > 0  # cheap companies did better in this panel
    assert not [line for line in lines if not line.trusted]


def _store(api: SimpleNamespace, model: MiningModel, signals) -> None:
    month = last_month(signals)
    found = run_findings(signals, model, date(2026, 10, 30))
    with api.uow_factory() as uow:
        uow.catalog.upsert(
            [
                CatalogInstrument(
                    ticker=t,
                    name=f"Cia {t}",
                    asset_type=AssetType.STOCK_BR,
                    sector="S",
                    volume_brl=5e6,
                )
                for t in signals
            ]
        )
        uow.cvm_issuers.replace_all(
            [IssuerTicker(t, f"{i:014d}", t) for i, t in enumerate(signals, 1)]
        )
        uow.mining.replace_signals(
            [
                MiningSignal(t, month_end(month), name, z)
                for t, by_month in signals.items()
                for name, z in by_month[month].items()
            ]
        )
        uow.mining.replace_run(date(2026, 10, 30), found)
        uow.forecasts.save_model(MINING, date(2026, 10, 30), model.to_dict())
        uow.commit()


def test_overview_why_and_follow(api: SimpleNamespace, real) -> None:
    signals, _alphas, _forward, model = real
    assert api.client.get("/api/v1/research/mining").json()["status"] == "NOT_RUN"
    _store(api, model, signals)
    data = api.client.get("/api/v1/research/mining").json()
    assert data["status"] == "OK" and data["trusted"] and len(data["findings"]) == FINDINGS
    first = data["findings"][0]
    assert first["company"] == f"Cia {first['ticker']}" and first["asset_id"] is None
    assert {w["signal"] for w in data["weights"]} == {VALUE, QUALITY, IMPROVEMENT, MOMENTUM}

    why = api.client.get(f"/api/v1/research/mining/why/{first['ticker']}").json()
    assert why["status"] == "FOUND" and why["rank"] == 1
    last = data["findings"][-1]["ticker"]
    outsider = next(
        t for t in signals if t not in {f["ticker"] for f in data["findings"]} and t != last
    )
    other = api.client.get(f"/api/v1/research/mining/why/{outsider}").json()
    assert other["status"] == "RANKED" and other["rank"] > FINDINGS
    assert other["score_annual"] <= other["cutoff_annual"]
    assert api.client.get("/api/v1/research/mining/why/XPTO3").json()["status"] == "NOT_IN_UNIVERSE"

    # Following a finding registers it; the overview links to the asset.
    followed = api.client.post(
        "/api/v1/research/watchlist", json={"ticker": first["ticker"], "asset_type": "STOCK_BR"}
    )
    assert followed.status_code in (200, 201)
    again = api.client.get("/api/v1/research/mining").json()["findings"][0]
    assert again["asset_id"] == followed.json()["asset_id"]


def test_mining_mcp(api: SimpleNamespace, real) -> None:
    signals, _alphas, _forward, model = real
    _store(api, model, signals)
    handlers = AgenticRuntimeHandlers(
        uow_factory=api.uow_factory,
        portfolio_service=PortfolioApplicationService(offline_gateway()),
    )
    overview = CATALOG_BY_NAME["research.mining"]
    assert len(overview.invoke(handlers, overview.input_model()).findings) == FINDINGS
    why = CATALOG_BY_NAME["research.mining_why"]
    assert why.invoke(handlers, why.input_model(ticker="XPTO3")).status == "NOT_IN_UNIVERSE"
    rec = CATALOG_BY_NAME["research.mining_record"]
    assert rec.invoke(handlers, rec.input_model()).lines == []


def test_mining_alert_is_opt_in(api: SimpleNamespace, real) -> None:
    from dataclasses import replace

    from domain.alerts.services.evaluator import AlertKind, mining_alerts
    from domain.alerts.services.use_cases import AlertHandler

    signals, _alphas, _forward, model = real
    _store(api, model, signals)
    service = PortfolioApplicationService(offline_gateway())
    off = AlertHandler(uow_factory=api.uow_factory, portfolio_service=service)
    assert not [a for a in off.list_alerts().alerts if a.kind == AlertKind.MINING_FINDING]
    on = AlertHandler(uow_factory=api.uow_factory, portfolio_service=service, mining_alerts=True)
    shown = [a for a in on.list_alerts().alerts if a.kind == AlertKind.MINING_FINDING]
    assert len(shown) == FINDINGS and all(a.route == "/research/mining" for a in shown)
    # A followed ticker and an untrusted ranking raise nothing.
    found = run_findings(signals, model, date(2026, 10, 30))
    assert len(mining_alerts(found, [found[0].ticker])) == FINDINGS - 1
    assert mining_alerts([replace(f, trusted=False) for f in found], []) == []
