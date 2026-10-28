"""Phase 33.1: simulation history loading, coverage report and the database-built history."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from domain.agentic.services.catalog import CATALOG_BY_NAME, AgenticRuntimeHandlers
from domain.market.entities import PricePoint
from domain.portfolio.services.service import PortfolioApplicationService
from domain.shared.entities import CatalogInstrument, MarketSeriesPoint
from domain.shared.enums import AssetType, Market, SeriesUnit
from domain.simulation.data import (
    FX_USDBRL,
    CoverageStatus,
    build_market_history,
    index_symbol,
    px_symbol,
    series_coverage,
    simulation_universe,
    tr_symbol,
)
from domain.simulation.market import month_ends
from infra.providers.yfinance_provider import YFinanceProvider
from tests.conftest import offline_gateway
from worker.jobs import sync_simulation_history_job

START = date(2024, 1, 2)
END = date(2024, 12, 31)


# --- provider ------------------------------------------------------------------------------


class _Ticker:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.calls: list[dict[str, Any]] = []

    def history(self, **kwargs: Any) -> pd.DataFrame:
        self.calls.append(kwargs)
        index = pd.to_datetime(["2024-01-02", "2024-01-03"])
        return pd.DataFrame(
            {"Close": [10.0, 11.0], "Adj Close": [9.0, 10.5], "Volume": [100, 200]}, index=index
        )


def test_full_history_keeps_split_and_total_return_closes() -> None:
    tickers: dict[str, _Ticker] = {}

    def factory(symbol: str) -> _Ticker:
        tickers[symbol] = _Ticker(symbol)
        return tickers[symbol]

    provider = YFinanceProvider(ticker_factory=factory)
    points = provider.get_full_history("WEGE3", market=Market.B3, start=date(2024, 1, 1))

    assert [(p.close, p.adj_close) for p in points] == [(10.0, 9.0), (11.0, 10.5)]
    call = tickers["WEGE3.SA"].calls[0]
    assert call["auto_adjust"] is False
    assert call["start"] == "2024-01-01"
    assert provider.get_full_history("WEGE3", market=Market.B3)  # period="max" path


def test_full_history_failure_returns_empty() -> None:
    class _Broken:
        def history(self, **_kw: Any) -> pd.DataFrame:
            raise RuntimeError("blocked")

    provider = YFinanceProvider(ticker_factory=lambda _s: _Broken())
    assert provider.get_full_history("WEGE3", market=Market.B3) == []


# --- coverage --------------------------------------------------------------------------------


def test_series_coverage_states() -> None:
    full = month_ends(START, END)
    ok = series_coverage("A", "A", full, START, END)
    late = series_coverage("B", "B", full[6:], START, END)
    holed = series_coverage("C", "C", full[:3] + full[5:], START, END)
    none = series_coverage("D", "D", [], START, END)

    assert ok.status == CoverageStatus.OK and ok.share == 1.0
    assert late.status == CoverageStatus.PARTIAL and "Começa em" in (late.note or "")
    assert holed.status == CoverageStatus.PARTIAL and holed.longest_gap_days > 31
    assert none.status == CoverageStatus.MISSING and none.months_expected == 12


# --- database-built history ------------------------------------------------------------------


class _Series:
    def __init__(self, data: dict[str, list[tuple[date, float, SeriesUnit]]]) -> None:
        self.data = data

    def list_series(
        self, symbol: str, *, date_from: date | None = None, date_to: date | None = None
    ):  # noqa: ANN201
        return [
            MarketSeriesPoint(symbol=symbol, reference_date=d, value=v, unit=u)
            for d, v, u in self.data.get(symbol.upper(), [])
            if (date_from is None or d >= date_from) and (date_to is None or d <= date_to)
        ]


def test_market_history_converts_usd_and_builds_the_cdi_index() -> None:
    days = [date(2024, 1, 2), date(2024, 1, 3)]
    price = SeriesUnit.PRICE
    repo = _Series(
        {
            tr_symbol("WEGE3"): [(days[0], 40.0, price), (days[1], 41.0, price)],
            tr_symbol("AAPL"): [(days[0], 100.0, price), (days[1], 110.0, price)],
            FX_USDBRL: [(days[0], 5.0, price)],
            index_symbol("SP500TR"): [(days[0], 1000.0, SeriesUnit.INDEX_POINTS)],
            "IFIX": [(days[0], 3000.0, SeriesUnit.INDEX_POINTS)],
            "CDI": [(d, 0.04, SeriesUnit.PERCENT_PER_DAY) for d in days],
            "IPCA": [(date(2024, 1, 1), 0.4, SeriesUnit.PERCENT_PER_MONTH)],
        }
    )

    history = build_market_history(
        repo,
        ["WEGE3", "AAPL", "NONE3"],
        start=days[0],
        end=days[1],
        currency_by_ticker={"AAPL": "USD"},
    )
    view = history.view(days[1])

    assert view.price("WEGE3") == 41.0
    assert view.price("AAPL") == pytest.approx(110.0 * 5.0)  # last known dollar carried over
    assert view.price("SP500_BRL") == pytest.approx(5000.0)
    assert view.price("IFIX") == 3000.0
    assert view.price("CDI") == pytest.approx(1.0004**2)
    assert history.ipca_monthly[(2024, 1)] == pytest.approx(0.004)
    assert "NONE3" not in history.series


# --- worker job and route --------------------------------------------------------------------


class _HistoryGateway:
    def __init__(self) -> None:
        self.requests: list[tuple[str, Any]] = []

    def get_full_history(self, symbol: str, **kwargs: Any) -> list[PricePoint]:
        self.requests.append((symbol, kwargs))
        return [
            PricePoint(date=date(2024, 1, 2), close=10.0, adj_close=9.0),
            PricePoint(date=date(2024, 1, 3), close=11.0, adj_close=10.0),
        ]

    def fetch_bcb_series(self, symbol: str, start_date: date, end_date: date):  # noqa: ANN201
        return [
            MarketSeriesPoint(
                symbol=symbol,
                reference_date=start_date,
                value=0.04,
                unit=SeriesUnit.PERCENT_PER_DAY,
            )
        ]


def test_universe_takes_portfolio_watchlist_and_top_catalog(api: SimpleNamespace) -> None:
    api.client.post(
        "/api/v1/assets", json={"ticker": "WEGE3", "name": "WEG", "asset_type": "STOCK_BR"}
    )
    api.client.post(
        "/api/v1/assets",
        json={"ticker": "CAIXA", "name": "Caixa", "asset_type": "CASH", "manual_price": "1"},
    )
    with api.uow_factory() as uow:
        uow.catalog.upsert(
            [
                CatalogInstrument("PETR4", "Petrobras", AssetType.STOCK_BR, volume_brl=9e9),
                CatalogInstrument("ITUB4", "Itaú", AssetType.STOCK_BR, volume_brl=5e9),
                CatalogInstrument("WEGE3", "WEG", AssetType.STOCK_BR, volume_brl=8e9),
            ]
        )
        uow.commit()
        tickers = [a.ticker for a in simulation_universe(uow, catalog_top=1)]
    assert tickers == ["WEGE3", "PETR4"]  # CAIXA has no market history; WEGE3 not duplicated


def test_sync_job_stores_total_return_and_split_closes(api: SimpleNamespace) -> None:
    api.client.post(
        "/api/v1/assets", json={"ticker": "WEGE3", "name": "WEG", "asset_type": "STOCK_BR"}
    )
    gateway = _HistoryGateway()

    counts = sync_simulation_history_job(
        api.uow_factory,
        gateway,
        as_of_date=date(2024, 12, 31),
        catalog_top=0,
        start=date(2024, 1, 2),  # type: ignore[arg-type]
    )

    assert counts["WEGE3"] == 2 and counts["IBOV"] == 2 and counts["USDBRL"] == 2
    assert counts["CDI"] >= 1
    assert {s for s, _ in gateway.requests} == {"WEGE3", "^BVSP", "^SP500TR", "USDBRL=X"}
    with api.uow_factory() as uow:
        assert [p.value for p in uow.market_series.list_series(tr_symbol("WEGE3"))] == [9.0, 10.0]
        assert [p.value for p in uow.market_series.list_series(px_symbol("WEGE3"))] == [10.0, 11.0]

    # Reloading rewrites the whole series (dividend adjustments rescale the past).
    gateway.get_full_history = lambda symbol, **_kw: [  # type: ignore[method-assign]
        PricePoint(date=date(2024, 1, 2), close=10.0, adj_close=8.5)
    ]
    sync_simulation_history_job(
        api.uow_factory,
        gateway,
        as_of_date=date(2024, 12, 31),
        catalog_top=0,
        start=date(2024, 1, 2),  # type: ignore[arg-type]
    )
    with api.uow_factory() as uow:
        assert uow.market_series.list_series(tr_symbol("WEGE3"))[0].value == 8.5


def test_coverage_route_and_mcp(api: SimpleNamespace) -> None:
    api.client.post(
        "/api/v1/assets", json={"ticker": "WEGE3", "name": "WEG", "asset_type": "STOCK_BR"}
    )
    with api.uow_factory() as uow:
        uow.market_series.upsert_points(
            tr_symbol("WEGE3"), [(d, 40.0) for d in month_ends(START, END)], unit=SeriesUnit.PRICE
        )
        uow.commit()

    body = api.client.get(f"/api/v1/simulations/coverage?start={START}&end={END}").json()
    by_key = {s["key"]: s for s in body["series"]}
    assert by_key["WEGE3"]["status"] == "OK"
    assert by_key["USDBRL"]["status"] == "MISSING"
    assert "USDBRL" in body["missing"]
    bad = api.client.get(f"/api/v1/simulations/coverage?start={END}&end={START}")
    assert bad.status_code == 400

    op = CATALOG_BY_NAME["simulation.coverage"]
    handlers = AgenticRuntimeHandlers(
        uow_factory=api.uow_factory,
        portfolio_service=PortfolioApplicationService(offline_gateway()),
    )
    result = op.invoke(handlers, op.input_model(start=START, end=END))
    assert op.kind == "query" and any(s.key == "WEGE3" for s in result.series)
