"""Phase 43.1: the Garimpo universe and the long histories of its stocks."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from domain.agentic.services.catalog import CATALOG_BY_NAME, AgenticRuntimeHandlers
from domain.disclosures.entities import IssuerTicker
from domain.market.entities import Fundamentals, PricePoint
from domain.portfolio.services.service import PortfolioApplicationService
from domain.shared.entities import CatalogInstrument
from domain.shared.enums import AssetType, SeriesUnit
from domain.simulation.data import px_symbol, split_symbol, tr_symbol
from tests.conftest import offline_gateway
from worker.jobs import sync_mining_universe_job

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
TODAY = NOW.date()


def _seed(api: SimpleNamespace) -> None:
    def stock(ticker, volume, sector="Bens Industriais"):
        return CatalogInstrument(
            ticker=ticker,
            name=ticker,
            asset_type=AssetType.STOCK_BR,
            sector=sector,
            volume_brl=volume,
        )

    with api.uow_factory() as uow:
        uow.catalog.upsert(
            [
                stock("WEGE3", 50e6),
                stock("PETR3", 90e6, "Petróleo"),
                stock("PETR4", 400e6, "Petróleo"),
                stock("TINY3", 200e3),  # below the floor
                stock("NOMAP3", 30e6),  # no CNPJ in the CVM map
                CatalogInstrument(
                    ticker="HGLG11", name="HGLG11", asset_type=AssetType.FII, volume_brl=9e6
                ),
            ]
        )
        uow.cvm_issuers.replace_all(
            [
                IssuerTicker("WEGE3", "84429695000111", "WEG"),
                IssuerTicker("PETR3", "33000167000101", "PETROBRAS"),
                IssuerTicker("PETR4", "33000167000101", "PETROBRAS"),
                IssuerTicker("TINY3", "11111111000111", "TINY"),
            ]
        )
        # The stored average beats the last session: WEGE3 trades R$ 60 million a day.
        uow.market_data.save_fundamentals(
            {"WEGE3": Fundamentals(symbol="WEGE3", avg_daily_volume=60e6)}, fetched_at=NOW
        )
        uow.commit()


def test_universe_is_liquid_mapped_and_one_class_per_company(api: SimpleNamespace) -> None:
    _seed(api)
    data = api.client.get("/api/v1/research/mining/universe").json()
    members = {m["ticker"]: m for m in data["members"]}
    assert list(members) == ["PETR4", "WEGE3"]  # most liquid first; PETR3 is the same company
    assert members["WEGE3"]["daily_volume"] == 60e6
    assert members["WEGE3"]["volume_source"] == "AVERAGE"
    assert members["PETR4"]["volume_source"] == "LAST_SESSION"
    assert data["min_daily_volume"] == 1_000_000 and data["with_history"] == 0


def test_history_loader_fills_the_stalest_first(api: SimpleNamespace) -> None:
    _seed(api)
    with api.uow_factory() as uow:  # WEGE3 is fresh: loaded three days ago
        uow.market_series.upsert_points(
            px_symbol("WEGE3"), [(TODAY - timedelta(days=3), 50.0)], unit=SeriesUnit.PRICE
        )
        uow.commit()
    gateway = offline_gateway()
    calls: list[str] = []

    def full_history(symbol, **kw):
        calls.append(symbol)
        return [
            PricePoint(date=date(2024, 1, 2), close=20.0, adj_close=18.0),
            PricePoint(date=date(2024, 6, 3), close=10.0, adj_close=9.5, split=2.0),
        ]

    gateway.get_full_history = full_history
    details = sync_mining_universe_job(api.uow_factory, gateway, as_of_date=TODAY, batch=5)
    assert calls == ["PETR4"]
    assert details == {
        "universe": 2,
        "fresh": 1,
        "loaded": 1,
        "without_history": [],
        "remaining": 0,
    }
    with api.uow_factory() as uow:
        assert uow.market_series.date_range(tr_symbol("PETR4")) == (
            date(2024, 1, 2),
            date(2024, 6, 3),
        )
        assert [p.value for p in uow.market_series.list_series(split_symbol("PETR4"))] == [2.0]
    data = api.client.get("/api/v1/research/mining/universe").json()
    assert data["with_history"] == 2


def test_history_loader_respects_the_batch(api: SimpleNamespace) -> None:
    _seed(api)
    gateway = offline_gateway()
    gateway.get_full_history = lambda symbol, **kw: []
    details = sync_mining_universe_job(api.uow_factory, gateway, as_of_date=TODAY, batch=1)
    assert details["loaded"] == 0 and details["without_history"] == ["PETR4"]
    assert details["remaining"] == 1


def test_universe_mcp(api: SimpleNamespace) -> None:
    _seed(api)
    handlers = AgenticRuntimeHandlers(
        uow_factory=api.uow_factory,
        portfolio_service=PortfolioApplicationService(offline_gateway()),
    )
    op = CATALOG_BY_NAME["research.mining_universe"]
    assert [m.ticker for m in op.invoke(handlers, op.input_model()).members] == ["PETR4", "WEGE3"]
