"""The projection lens covers catalog stocks (analysis P0, item 3)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from domain.recommendation.keys import PROJECTION
from tests.conftest import offline_gateway
from tests.test_mining_signals import seed_panel
from worker.jobs import refresh_asset_forecasts_job, refresh_asset_lenses_job, run_mining_job

NOW = datetime(2024, 3, 1, 21, tzinfo=UTC)  # right after the last seeded price


def test_liquid_catalog_stocks_get_a_forecast_and_the_projection_lens(
    api: SimpleNamespace,
) -> None:
    companies = seed_panel(api)
    without = refresh_asset_forecasts_job(api.uow_factory, offline_gateway(), now=NOW)
    assert without["forecasts"] == 0  # nothing registered: no forecast
    found = refresh_asset_forecasts_job(
        api.uow_factory, offline_gateway(), min_daily_volume=1_000_000.0, now=NOW
    )
    assert found["forecasts"] + found["insufficient"] > 0
    with api.uow_factory() as uow:
        stored = {t: uow.forecasts.latest(t) for t in companies}
    assert any(s is not None for s in stored.values())

    run_mining_job(api.uow_factory, offline_gateway(), now=NOW)
    refresh_asset_lenses_job(api.uow_factory, offline_gateway(), now=NOW)
    with api.uow_factory() as uow:
        lenses = {i.ticker: i for i in uow.recommendation.lenses()}
    forecasted = [t for t, s in stored.items() if s is not None and s.payload.get("status") == "OK"]
    assert forecasted, stored
    assert any(lenses[t].lens(PROJECTION).value is not None for t in forecasted if t in lenses)
