"""Unit and integration tests for background Worker jobs and APScheduler configuration."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from domain.shared.entities import AssetEntity, TransactionEntity
from domain.shared.enums import ArcaClass, AssetType, TransactionKind
from infra.cache.redis_cache import InMemoryCache
from infra.data.unit_of_work import SqlAlchemyUnitOfWork
from infra.providers.bcb import BcbSgsProvider
from infra.providers.brapi import BrapiProvider
from infra.providers.gateway import CachedMarketGateway
from infra.providers.yfinance_provider import YFinanceProvider
from worker.jobs import (
    record_daily_snapshot_job,
    sync_bcb_and_benchmarks_job,
    warm_portfolio_quotes_job,
)
from worker.scheduler import create_scheduler


class _WorkerFakeTicker:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.info: dict[str, Any] = {
            "regularMarketPrice": 5.10 if symbol == "USDBRL=X" else 128000.0,
            "previousClose": 5.08 if symbol == "USDBRL=X" else 127000.0,
            "currency": "BRL",
        }

    def history(self, period: str = "1y", interval: str = "1d") -> Any:
        import pandas as pd

        idx = pd.to_datetime(["2025-01-02", "2025-01-03"])
        return pd.DataFrame(
            {
                "Open": [120000.0, 121000.0],
                "High": [121500.0, 122500.0],
                "Low": [119500.0, 120500.0],
                "Close": [121000.0, 122000.0],
                "Volume": [10000.0, 12000.0],
            },
            index=idx,
        )


def test_worker_jobs_and_scheduler_integration(tmp_path: Path, monkeypatch) -> None:
    db_file = tmp_path / "worker_test.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    persistence_dir = Path(__file__).resolve().parents[1]
    alembic_cfg = Config(str(persistence_dir / "alembic.ini"))
    alembic_cfg.set_main_option(
        "script_location", str(persistence_dir / "infra" / "data" / "migrations")
    )
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(db_url, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    uow_factory = lambda: SqlAlchemyUnitOfWork(session_factory=factory)  # noqa: E731

    with uow_factory() as uow:
        asset = uow.assets.add(
            AssetEntity(
                ticker="ITUB4",
                name="Itaú Unibanco",
                asset_type=AssetType.STOCK_BR,
                arca_class=ArcaClass.ACOES,
            )
        )
        assert asset.id is not None
        uow.transactions.add(
            TransactionEntity(
                asset_id=asset.id,
                kind=TransactionKind.BUY,
                trade_date=date(2025, 1, 3),
                quantity=Decimal("100"),
                unit_price=Decimal("32.00"),
            )
        )
        uow.commit()

    def brapi_mock(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "symbol": "ITUB4",
                        "longName": "Itaú Unibanco",
                        "currency": "BRL",
                        "regularMarketPrice": 35.0,
                    }
                ]
            },
        )

    def bcb_mock(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"data": "02/01/2025", "valor": "0.041"},
                {"data": "03/01/2025", "valor": "0.041"},
            ],
        )

    gateway = CachedMarketGateway(
        brapi=BrapiProvider(client=httpx.Client(transport=httpx.MockTransport(brapi_mock))),
        yfinance=YFinanceProvider(ticker_factory=_WorkerFakeTicker),
        bcb=BcbSgsProvider(client=httpx.Client(transport=httpx.MockTransport(bcb_mock))),
        cache=InMemoryCache(),
    )

    counts = sync_bcb_and_benchmarks_job(uow_factory, gateway, as_of_date=date(2025, 1, 5))
    assert counts["CDI"] == 2
    assert counts["IBOV"] == 2
    assert counts["IFIX"] == 2

    warmed = warm_portfolio_quotes_job(uow_factory, gateway)
    assert warmed == 1

    snap = record_daily_snapshot_job(uow_factory, gateway, snapshot_date=date(2025, 1, 3))
    assert snap.invested_value == 3200.0
    assert snap.market_value == 3500.0
    assert snap.net_flow == 3200.0

    sched = create_scheduler(gateway)
    job_ids = {job.id for job in sched.get_jobs()}
    assert {
        "warm_portfolio_quotes",
        "sync_bcb_and_benchmarks",
        "record_daily_snapshot",
    }.issubset(job_ids)
    engine.dispose()
