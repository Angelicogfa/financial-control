"""Price history by period for the asset chart (6 months to everything)."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from domain.agentic.services.catalog import CATALOG_BY_NAME
from domain.market.entities import PricePoint
from domain.market.services.price_chart import price_chart, thin
from infra.providers.gateway import CachedMarketGateway


def _series(values: list[float], start: date = date(2020, 1, 1)) -> list[PricePoint]:
    return [PricePoint(date=start + timedelta(days=i), close=v) for i, v in enumerate(values)]


def test_thin_keeps_first_and_last_and_the_limit() -> None:
    points = [(date(2020, 1, 1) + timedelta(days=i), float(i)) for i in range(5000)]
    thinned = thin(points, 500)
    assert len(thinned) == 500
    assert thinned[0] == points[0] and thinned[-1] == points[-1]
    assert thin(points[:10], 500) == points[:10]


def test_price_chart_summary_on_the_clean_daily_series() -> None:
    # 10 -> 20 with a bad print of 0.2 that comes back (dropped) and a real high of 25.
    values = [10.0, 11.0, 0.2, 12.0, 25.0, 18.0, 20.0]
    chart = price_chart("1y", list(reversed(_series(values))))
    assert chart.dropped_spikes == 1
    assert [c for _, c in chart.points] == [10.0, 11.0, 12.0, 25.0, 18.0, 20.0]
    assert chart.change == pytest.approx(1.0)
    assert chart.high == (date(2020, 1, 5), 25.0)
    assert chart.low == (date(2020, 1, 1), 10.0)


def test_price_chart_without_data() -> None:
    chart = price_chart("max", [])
    assert chart.points == [] and chart.change is None and chart.high is None


def test_prices_route_by_period(api: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[str] = []

    def fake_history(self, symbol, *, range_period="1y", **_kw):  # noqa: ANN001, ANN202
        asked.append(range_period)
        return _series([10.0 + i * 0.01 for i in range(2000)])

    monkeypatch.setattr(CachedMarketGateway, "get_history", fake_history)
    asset = api.client.post(
        "/api/v1/assets", json={"ticker": "WEGE3", "name": "WEG", "asset_type": "STOCK_BR"}
    ).json()

    body = api.client.get(f"/api/v1/assets/{asset['id']}/prices", params={"range": "5y"}).json()
    assert asked == ["5y"]
    assert body["range"] == "5y" and len(body["points"]) == 500
    assert body["points"][0] == {"date": "2020-01-01", "close": 10.0}
    assert body["change"] == pytest.approx(29.99 / 10.0 - 1.0)
    assert body["high"]["price"] == pytest.approx(29.99)

    default = api.client.get(f"/api/v1/assets/{asset['id']}/prices").json()
    assert default["range"] == "1y"
    assert (
        api.client.get(f"/api/v1/assets/{asset['id']}/prices", params={"range": "3y"}).status_code
        == 422
    )
    assert api.client.get("/api/v1/assets/9999/prices").status_code == 404


def test_prices_is_an_mcp_query() -> None:
    op = CATALOG_BY_NAME["assets.prices"]
    assert op.kind == "query"
    assert op.input_model(asset_id=1).range == "1y"
