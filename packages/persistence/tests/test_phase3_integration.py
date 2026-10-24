"""Phase 3 integration tests: CachedMarketGateway + SqlAlchemyUnitOfWork + Benchmark Analytics."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config
from fincontrol_core.analytics import (
    analyze_return_series,
    simple_returns,
    time_weighted_return,
)
from fincontrol_core.domain.entities import PortfolioSnapshotEntity
from fincontrol_core.domain.enums import SeriesUnit
from fincontrol_core.market.bcb import BcbSgsProvider
from fincontrol_core.market.brapi import BrapiProvider
from fincontrol_core.market.cache import InMemoryCache
from fincontrol_core.market.gateway import CachedMarketGateway
from fincontrol_persistence.unit_of_work import SqlAlchemyUnitOfWork
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def test_phase3_gateway_persistence_and_analytics_integration(tmp_path: Path, monkeypatch) -> None:
    db_file = tmp_path / "phase3_test.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    persistence_dir = Path(__file__).resolve().parents[1]
    alembic_cfg = Config(str(persistence_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(persistence_dir / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(db_url, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def mock_bcb(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"data": "02/01/2025", "valor": "0.041"},
                {"data": "03/01/2025", "valor": "0.041"},
                {"data": "06/01/2025", "valor": "0.041"},
            ],
        )

    gateway = CachedMarketGateway(
        brapi=BrapiProvider(client=httpx.Client(transport=httpx.MockTransport(mock_bcb))),
        bcb=BcbSgsProvider(client=httpx.Client(transport=httpx.MockTransport(mock_bcb))),
        cache=InMemoryCache(),
    )

    cdi_series = gateway.fetch_bcb_series("CDI", date(2025, 1, 1), date(2025, 1, 10))
    assert len(cdi_series) == 3

    with SqlAlchemyUnitOfWork(session_factory=factory) as uow:
        uow.market_series.upsert_points(
            "CDI",
            [(p.reference_date, p.value) for p in cdi_series],
            unit=SeriesUnit.PERCENT_PER_DAY,
        )
        uow.market_series.upsert_points(
            "IBOV",
            [
                (date(2025, 1, 2), 120000.0),
                (date(2025, 1, 3), 121200.0),
                (date(2025, 1, 6), 122412.0),
            ],
            unit=SeriesUnit.INDEX_POINTS,
        )
        uow.market_series.upsert_points(
            "IFIX",
            [
                (date(2025, 1, 2), 3100.0),
                (date(2025, 1, 3), 3115.5),
                (date(2025, 1, 6), 3131.0),
            ],
            unit=SeriesUnit.INDEX_POINTS,
        )
        uow.snapshots.upsert(
            PortfolioSnapshotEntity(
                snapshot_date=date(2025, 1, 2),
                invested_value=50000.0,
                market_value=50000.0,
                unrealized_pnl=0.0,
                net_flow=0.0,
            )
        )
        uow.snapshots.upsert(
            PortfolioSnapshotEntity(
                snapshot_date=date(2025, 1, 3),
                invested_value=50000.0,
                market_value=50600.0,
                unrealized_pnl=600.0,
                net_flow=0.0,
            )
        )
        uow.snapshots.upsert(
            PortfolioSnapshotEntity(
                snapshot_date=date(2025, 1, 6),
                invested_value=55000.0,
                market_value=56200.0,
                unrealized_pnl=1200.0,
                net_flow=5000.0,
            )
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory=factory) as uow:
        persisted_snapshots = uow.snapshots.list_range(
            date_from=date(2025, 1, 1), date_to=date(2025, 1, 10)
        )
        persisted_ibov = uow.market_series.list_series(
            "IBOV", date_from=date(2025, 1, 1), date_to=date(2025, 1, 10)
        )
        persisted_ifix = uow.market_series.list_series(
            "IFIX", date_from=date(2025, 1, 1), date_to=date(2025, 1, 10)
        )

    port_returns = time_weighted_return(persisted_snapshots)
    ibov_returns = simple_returns([p.value for p in persisted_ibov])
    ifix_returns = simple_returns([p.value for p in persisted_ifix])

    summary = analyze_return_series(
        port_returns,
        benchmark_returns_map={"IBOV": ibov_returns, "IFIX": ifix_returns},
    )
    assert summary.observations == 2
    assert summary.cumulative_return > 0.02
    assert len(summary.benchmarks) == 4  # IBOV, IFIX, CDI, IPCA
    engine.dispose()
