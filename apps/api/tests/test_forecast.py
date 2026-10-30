"""Phase 42.1: probabilistic price forecast per asset (layer A), its calibration and seal."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from domain.agentic.services.catalog import CATALOG_BY_NAME, AgenticRuntimeHandlers
from domain.disclosures.entities import IssuerTicker
from domain.disclosures.events import BUYBACK
from domain.forecast.calibration import ForecastCalibration
from domain.forecast.event_runs import EVENTS
from domain.forecast.events import RecentEvent
from domain.forecast.model import (
    QUANTILE_LEVELS,
    PriceForecast,
    chance_above,
    dividend_drag,
    forecast_asset,
)
from domain.policy.services.policy import ArcaPolicy, ClassPolicy, InvestmentPolicy
from domain.portfolio.services.service import PortfolioApplicationService
from domain.shared.enums import ArcaClass, SeriesUnit
from domain.simulation.candidates import FactorFit, ols_fit, shrink
from domain.simulation.data import index_symbol, px_symbol, tr_symbol
from tests.conftest import offline_gateway
from tests.test_cvm_events import WEG, _doc, _passed_study
from worker.jobs import calibrate_forecasts_job, refresh_asset_forecasts_job

A, CX = ArcaClass.ACOES, ArcaClass.CAIXA
TODAY = date(2026, 10, 30)
NOW = datetime(2026, 10, 30, 20, 0, tzinfo=UTC)


def _fit(months: int = 120, noise: float = 0.0001) -> FactorFit:
    rng = np.random.default_rng(1)
    x = rng.normal(0.0, 0.05, months)
    y = 1.0 * x + rng.normal(0.0, noise, months)
    a, a_se, b, b_se, resid = ols_fit(y, x)
    return shrink(FactorFit("X", A, months, a, a_se, b, b_se, resid), 0.0)


# --- model ------------------------------------------------------------------------------------


def test_forecast_follows_the_class_the_cdi_and_the_dividends() -> None:
    forecast = forecast_asset(
        _fit(),
        np.full((400, 24), 0.01),
        cdi_monthly=0.01,
        price_now=100.0,
        drag_monthly=0.005,
        as_of=TODAY,
        seed=3,
    )
    assert [h.months for h in forecast.horizons] == [3, 6, 12, 24]
    year = next(h for h in forecast.horizons if h.months == 12)
    assert len(year.price_quantiles) == len(QUANTILE_LEVELS)
    assert year.price_quantiles == sorted(year.price_quantiles)
    # About 2% a month in total return, minus the 0.5% a month paid as dividends.
    assert 115.0 < year.price_at(0.5) < 130.0
    assert year.total_return_p50 > year.price_at(0.5) / 100.0 - 1.0
    assert year.up.value > 0.99 and year.fall_20.value < 0.01
    assert year.up.low <= year.up.value <= year.up.high
    keys = [d.key for d in forecast.drivers]
    assert keys == ["MARKET", "OWN", "VALUATION", "EVENTS"]
    assert PriceForecast.from_dict(forecast.to_dict()) == forecast


def test_a_recent_event_moves_the_first_month() -> None:
    args = {
        "cdi_monthly": 0.01,
        "price_now": 100.0,
        "drag_monthly": 0.0,
        "as_of": TODAY,
        "seed": 3,
    }
    base = forecast_asset(_fit(), np.full((400, 24), 0.0), **args)
    assert base.drivers[3].annual is None and "Nenhum evento" in base.drivers[3].note
    used = RecentEvent(BUYBACK, date(2026, 10, 26), 4, 0.05, 0.0, 2.0, True, "Recompra: +5%.")
    ignored = RecentEvent("DIVIDENDS", date(2026, 10, 27), 3, 0.0, 0.0, 1.0, False, "Sem efeito.")
    moved = forecast_asset(_fit(), np.full((400, 24), 0.0), **args, events=[used, ignored])
    first = next(h for h in moved.horizons if h.months == 3)
    before = next(h for h in base.horizons if h.months == 3)
    assert first.price_at(0.5) == pytest.approx(before.price_at(0.5) * 1.05, rel=0.01)
    events = moved.drivers[3]
    assert events.key == "EVENTS" and events.annual == pytest.approx(0.05)
    assert events.note == "Recompra: +5%."
    assert moved.expected_total_return_annual > base.expected_total_return_annual
    only_ignored = forecast_asset(_fit(), np.full((400, 24), 0.0), **args, events=[ignored])
    assert only_ignored.drivers[3].annual is None and only_ignored.drivers[3].note == "Sem efeito."
    assert PriceForecast.from_dict(moved.to_dict()) == moved


def test_chance_above_reads_the_quantile_grid() -> None:
    grid = [float(i) for i in range(1, 100)]  # price = level x 100
    assert chance_above(grid, 50.0) == pytest.approx(0.5)
    assert chance_above(grid, 25.5) == pytest.approx(0.745)
    assert chance_above(grid, 0.5) == 0.995
    assert chance_above(grid, 150.0) == 0.005


def test_dividend_drag_is_the_gap_between_total_return_and_price() -> None:
    px = [100.0 * 1.01**t for t in range(37)]
    tr = [100.0 * (1.01 * 1.004) ** t for t in range(37)]
    assert dividend_drag(tr, px) == pytest.approx(np.log(1.004), rel=1e-6)
    assert dividend_drag(tr[:10], px[:10]) == 0.0  # less than a year: no estimate
    assert dividend_drag(px, tr) == 0.0  # never negative


# --- worker, API and MCP ----------------------------------------------------------------------


def _weekdays(years: int) -> list[date]:
    days, day = [], TODAY - timedelta(days=years * 365)
    while day <= TODAY:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def _seed(api: SimpleNamespace) -> dict[str, int]:
    days = _weekdays(9)
    rng = np.random.default_rng(4)
    ibov_returns = rng.normal(0.0004, 0.012, len(days))
    ibov = 100_000.0 * np.cumprod(1.0 + ibov_returns)
    wege = 40.0 * np.cumprod(1.0 + 0.0002 + 1.1 * ibov_returns + rng.normal(0.0, 0.008, len(days)))
    wege_px = wege / np.cumprod(np.full(len(days), 1.0001))  # about 2.5% a year of dividends
    short_days = days[-300:]  # about 14 months: below the 36-month minimum
    newb = 10.0 * np.cumprod(1.0 + rng.normal(0.001, 0.02, len(short_days)))
    ids = {}
    for ticker in ("WEGE3", "NEWB3"):
        ids[ticker] = api.client.post(
            "/api/v1/assets", json={"ticker": ticker, "name": ticker, "asset_type": "STOCK_BR"}
        ).json()["id"]
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
            px_symbol("WEGE3"), list(zip(days, wege_px, strict=True)), unit=SeriesUnit.PRICE
        )
        uow.market_series.upsert_points(
            tr_symbol("NEWB3"), list(zip(short_days, newb, strict=True)), unit=SeriesUnit.PRICE
        )
        uow.market_series.upsert_points(
            px_symbol("NEWB3"), list(zip(short_days, newb, strict=True)), unit=SeriesUnit.PRICE
        )
        uow.policies.add(
            InvestmentPolicy(
                arca=ArcaPolicy({c: ClassPolicy(target_pct=targets.get(c, 0.0)) for c in ArcaClass})
            )
        )
        uow.commit()
    return ids


def _trusted_calibration(api: SimpleNamespace) -> None:
    good = ForecastCalibration(
        as_of=TODAY,
        horizon_months=12,
        windows=400,
        effective_windows=100.0,
        assets=20,
        coverage_50=0.5,
        coverage_90=0.9,
        mean_pit=0.5,
        brier=0.22,
        brier_reference=0.25,
        first_origin=date(2015, 1, 31),
        last_origin=date(2025, 9, 30),
    )
    with api.uow_factory() as uow:
        uow.forecasts.save_calibration(TODAY, good.to_dict())
        uow.commit()


def test_forecast_statuses_through_the_api(api: SimpleNamespace) -> None:
    ids = _seed(api)
    url = f"/api/v1/assets/{ids['WEGE3']}/forecast"
    assert api.client.get(url).json()["status"] == "NOT_COMPUTED"

    counts = refresh_asset_forecasts_job(api.uow_factory, offline_gateway(), now=NOW)
    assert counts == {"forecasts": 1, "insufficient": 1, "skipped": 0}

    # Without a calibration the seal is empty and the forecast stays hidden.
    hidden = api.client.get(url).json()
    assert hidden["status"] == "LOW_CONFIDENCE" and hidden["seal"]["level"] == 0
    short = api.client.get(f"/api/v1/assets/{ids['NEWB3']}/forecast").json()
    assert short["status"] == "INSUFFICIENT_HISTORY" and short["months_used"] < 36

    _trusted_calibration(api)
    data = api.client.get(url).json()
    assert data["status"] == "OK" and data["seal"]["level"] == 4
    assert data["lead"].startswith("Em 12 meses, há ")
    assert data["dividend_yield_annual"] == pytest.approx(0.025, abs=0.01)
    year = next(h for h in data["horizons"] if h["months"] == 12)
    assert year["p5"] < year["p25"] < year["p50"] < year["p75"] < year["p95"]
    assert [t["key"] for t in year["thresholds"]] == ["NOW", "FALL_20"]  # nothing held
    assert year["thresholds"][0]["price"] == pytest.approx(data["price_now"])

    quality = api.client.get("/api/v1/market/forecast-quality").json()
    assert quality["status"] == "OK" and quality["coverage_90"] == 0.9
    assert api.client.get("/api/v1/assets/999/forecast").status_code == 404


def test_recent_events_reach_the_forecast(api: SimpleNamespace) -> None:
    ids = _seed(api)
    with api.uow_factory() as uow:
        uow.cvm_issuers.replace_all([IssuerTicker("WEGE3", WEG, "WEG")])
        uow.cvm_documents.upsert_many(
            [_doc("R1", date(2026, 10, 26), "Programa de Recompra de Ações")], seen_at=NOW
        )
        uow.forecasts.save_model(EVENTS, TODAY, _passed_study().to_dict())
        uow.commit()
    refresh_asset_forecasts_job(api.uow_factory, offline_gateway(), now=NOW)
    _trusted_calibration(api)
    data = api.client.get(f"/api/v1/assets/{ids['WEGE3']}/forecast").json()
    [event] = data["recent_events"]
    assert event["event_class"] == BUYBACK and event["used"] and event["days_after"] == 4
    assert event["label"] == "Recompra de ações" and event["effect"] > 0
    driver = next(d for d in data["drivers"] if d["key"] == "EVENTS")
    assert driver["annual"] == pytest.approx(event["effect"], abs=1e-4)
    assert data["model_version"] == "42.5.0"


def test_calibration_job_scores_the_past(api: SimpleNamespace) -> None:
    assert api.client.get("/api/v1/market/forecast-quality").json()["status"] == "NOT_COMPUTED"
    _seed(api)
    result = calibrate_forecasts_job(api.uow_factory, offline_gateway(), now=NOW)
    assert result["windows"] > 0 and result["assets"] >= 1
    assert 0.0 <= result["coverage_50"] <= result["coverage_90"] <= 1.0
    quality = api.client.get("/api/v1/market/forecast-quality").json()
    assert quality["status"] == "OK" and quality["windows"] == result["windows"]


def test_forecast_mcp(api: SimpleNamespace) -> None:
    ids = _seed(api)
    refresh_asset_forecasts_job(api.uow_factory, offline_gateway(), now=NOW)
    _trusted_calibration(api)
    handlers = AgenticRuntimeHandlers(
        uow_factory=api.uow_factory,
        portfolio_service=PortfolioApplicationService(offline_gateway()),
    )
    read = CATALOG_BY_NAME["assets.forecast"]
    assert read.kind == "query"
    data = read.invoke(handlers, read.input_model(asset_id=ids["WEGE3"]))
    assert data.status == "OK" and len(data.horizons) == 4
    quality = CATALOG_BY_NAME["market.forecast_quality"]
    assert quality.invoke(handlers, quality.input_model()).seal.level == 4


def test_one_asset_on_request_from_12_months_with_a_warning(api: SimpleNamespace) -> None:
    ids = _seed(api)
    url = f"/api/v1/assets/{ids['NEWB3']}/forecast"
    refresh_asset_forecasts_job(api.uow_factory, offline_gateway(), now=NOW)
    before = api.client.get(url).json()
    assert before["status"] == "INSUFFICIENT_HISTORY" and not before["requested"]
    assert "dá para pedir a previsão só deste ativo" in before["warnings"][0]

    # Asked for by itself: 14 months are enough, and it shows despite the empty seal.
    data = api.client.post(url).json()
    assert data["status"] == "OK" and data["requested"] and data["months_used"] < 36
    assert any(c.startswith("Histórico curto") for c in data["cautions"])
    assert any("foi pedida para este ativo" in c for c in data["cautions"])
    assert len(data["horizons"]) == 4
    # Only that asset was computed; the other stays hidden by the seal.
    wege = api.client.get(f"/api/v1/assets/{ids['WEGE3']}/forecast").json()
    assert wege["status"] == "LOW_CONFIDENCE" and not wege["requested"]

    # The daily run keeps following the asset the user asked for.
    tomorrow = NOW + timedelta(days=1)
    refresh_asset_forecasts_job(api.uow_factory, offline_gateway(), now=tomorrow)
    later = api.client.get(url).json()
    assert later["status"] == "OK" and later["requested"] and later["as_of"] == "2026-10-31"
    assert api.client.post("/api/v1/assets/999/forecast").status_code == 404


def test_on_request_without_any_stored_price(api: SimpleNamespace) -> None:
    _seed(api)
    days = _weekdays(2)
    asset_id = api.client.post(
        "/api/v1/assets", json={"ticker": "TRON3", "name": "TRON3", "asset_type": "STOCK_BR"}
    ).json()["id"]
    with api.uow_factory() as uow:  # total return only: no price series, no stored quote
        uow.market_series.upsert_points(
            tr_symbol("TRON3"),
            [(d, 10.0 + i * 0.01) for i, d in enumerate(days)],
            unit=SeriesUnit.PRICE,
        )
        uow.commit()
    response = api.client.post(f"/api/v1/assets/{asset_id}/forecast")
    assert response.status_code == 400 and response.json()["code"] == "FORECAST_NO_DATA"


def test_forecast_refresh_mcp(api: SimpleNamespace) -> None:
    ids = _seed(api)
    handlers = AgenticRuntimeHandlers(
        uow_factory=api.uow_factory,
        portfolio_service=PortfolioApplicationService(offline_gateway()),
    )
    command = CATALOG_BY_NAME["assets.forecast_refresh"]
    assert command.kind == "command"
    data = command.invoke(handlers, command.input_model(asset_id=ids["WEGE3"]))
    assert data.status == "OK" and data.requested
