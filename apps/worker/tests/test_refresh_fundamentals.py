"""Integration tests for the weekly statement refresh and its repository (item 11.1)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fincontrol_core.domain.entities import AssetEntity
from fincontrol_core.domain.enums import AssetType
from fincontrol_core.fundamentals.history import FundamentalPeriod, FundamentalSnapshot
from fincontrol_core.market.models import Fundamentals
from fincontrol_persistence.unit_of_work import SqlAlchemyUnitOfWork
from fincontrol_worker.jobs import record_checklist_evaluations_job, refresh_fundamentals_job
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

UoWFactory = Callable[[], SqlAlchemyUnitOfWork]


@pytest.fixture
def uow_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> UoWFactory:
    db_url = f"sqlite:///{(tmp_path / 'fundamentals.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    persistence_dir = Path(__file__).resolve().parents[3] / "packages" / "persistence"
    cfg = Config(str(persistence_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(persistence_dir / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")
    engine = create_engine(db_url, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return lambda: SqlAlchemyUnitOfWork(session_factory=factory)


class _StatementGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def get_annual_statements(
        self, symbol: str, *, asset_type: AssetType | None = None, bypass_cache: bool = False
    ) -> list[FundamentalSnapshot]:
        self.calls.append((symbol, asset_type))
        if symbol == "EMPTY3":
            return []
        return [
            FundamentalSnapshot(
                symbol, date(year, 12, 31), FundamentalPeriod.ANNUAL, {"revenue": float(year)}
            )
            for year in (2022, 2023)
        ]


def test_repository_upserts_by_key_and_lists_oldest_first(uow_factory: UoWFactory) -> None:
    first = FundamentalSnapshot(
        "wege3", date(2023, 12, 31), FundamentalPeriod.ANNUAL, {"revenue": 1.0}, source="brapi"
    )
    with uow_factory() as uow:
        uow.fundamentals.upsert([first])
        uow.fundamentals.upsert(
            [
                FundamentalSnapshot(
                    "WEGE3", date(2023, 12, 31), FundamentalPeriod.ANNUAL, {"revenue": 2.0}
                ),
                FundamentalSnapshot(
                    "WEGE3", date(2022, 12, 31), FundamentalPeriod.ANNUAL, {"revenue": 0.5}
                ),
            ]
        )
        uow.commit()

    with uow_factory() as uow:
        stored = uow.fundamentals.list_for("wege3")
        assert [(s.reference_date.year, s.value("revenue")) for s in stored] == [
            (2022, 0.5),
            (2023, 2.0),
        ]
        assert uow.fundamentals.list_for("WEGE3", period=FundamentalPeriod.TTM) == []
        assert uow.fundamentals.list_for_many([]) == {}


def test_refresh_job_covers_active_companies_and_extra_tickers(uow_factory: UoWFactory) -> None:
    with uow_factory() as uow:
        for ticker, asset_type, active in (
            ("WEGE3", AssetType.STOCK_BR, True),
            ("EMPTY3", AssetType.STOCK_BR, True),
            ("HGLG11", AssetType.FII, True),
            ("OLD3", AssetType.STOCK_BR, False),
        ):
            uow.assets.add(
                AssetEntity(ticker=ticker, name=ticker, asset_type=asset_type, is_active=active)
            )
        uow.commit()

    gateway = _StatementGateway()
    stored = refresh_fundamentals_job(uow_factory, gateway, extra_tickers=["itsa4"])  # type: ignore[arg-type]

    assert stored == {"EMPTY3": 0, "ITSA4": 2, "WEGE3": 2}
    assert {symbol for symbol, _ in gateway.calls} == {"EMPTY3", "ITSA4", "WEGE3"}
    with uow_factory() as uow:
        assert set(uow.fundamentals.list_for_many(["WEGE3", "ITSA4", "EMPTY3"])) == {
            "WEGE3",
            "ITSA4",
        }


def test_checklist_evaluations_are_recorded_only_when_they_change(
    uow_factory: UoWFactory,
) -> None:
    with uow_factory() as uow:
        stock = uow.assets.add(
            AssetEntity(ticker="WEGE3", name="WEG", asset_type=AssetType.STOCK_BR)
        )
        uow.assets.add(
            AssetEntity(
                ticker="CDB-X",
                name="CDB",
                asset_type=AssetType.CASH,
                cerrado_answers={"guarantee": True},
            )
        )
        uow.fundamentals.upsert(_StatementGateway().get_annual_statements("WEGE3"))
        uow.commit()

    class _Gateway:
        roe = 0.2

        def get_fundamentals(self, symbol: str, *, asset_type: AssetType | None = None) -> Any:
            return Fundamentals(symbol=symbol, return_on_equity=self.roe)

    gateway = _Gateway()
    assert record_checklist_evaluations_job(uow_factory, gateway) == 2  # type: ignore[arg-type]
    assert record_checklist_evaluations_job(uow_factory, gateway) == 0  # type: ignore[arg-type]
    gateway.roe = 0.01
    assert record_checklist_evaluations_job(uow_factory, gateway) == 1  # type: ignore[arg-type]

    with uow_factory() as uow:
        history = uow.checklists.evaluation_history(stock.id or 0)
    # Two fiscal years are too few for history rules: only the TTM ROE answers.
    assert [r.score for r in history] == [1, -1]


def test_catalog_sync_upserts_and_keeps_catalog_when_source_fails(
    uow_factory: UoWFactory,
) -> None:
    from fincontrol_core.domain.entities import CatalogInstrument
    from fincontrol_worker.jobs import sync_instrument_catalog_job

    class _CatalogGateway:
        def __init__(self, items: list[CatalogInstrument]) -> None:
            self.items = items

        def list_instruments(self) -> list[CatalogInstrument]:
            return self.items

    first = [
        CatalogInstrument("ITUB4", "Itau", AssetType.STOCK_BR, close=30.0, volume_brl=1e9),
        CatalogInstrument("HGLG11", "CSHG", AssetType.FII, volume_brl=None),
    ]
    assert sync_instrument_catalog_job(uow_factory, _CatalogGateway(first)) == 2  # type: ignore[arg-type]
    updated = [
        CatalogInstrument("ITUB4", "Itau PN", AssetType.STOCK_BR, close=31.0, volume_brl=2e6)
    ]
    assert sync_instrument_catalog_job(uow_factory, _CatalogGateway(updated)) == 1  # type: ignore[arg-type]
    assert sync_instrument_catalog_job(uow_factory, _CatalogGateway([])) == 0  # type: ignore[arg-type]

    with uow_factory() as uow:
        catalog = uow.catalog.list_all()
        itub = uow.catalog.get("itub4")
    assert [c.ticker for c in catalog] == ["ITUB4", "HGLG11"]
    assert itub is not None and (itub.name, itub.close) == ("Itau PN", 31.0)
    with uow_factory() as uow:
        assert uow.catalog.get("NONE3") is None
