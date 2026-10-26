"""Characterization tests for audit findings in background worker jobs.

Same convention as apps/packages/core/tests/test_audit_characterization.py: each test asserts
the correct behavior and stays `xfail(strict=True)` until its finding is fixed.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fincontrol_core.domain.entities import (
    AssetEntity,
    FixedIncomeTermEntity,
    PortfolioSnapshotEntity,
    TransactionEntity,
)
from fincontrol_core.domain.enums import (
    AssetType,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    TransactionKind,
)
from fincontrol_core.market.bcb import BcbSgsProvider
from fincontrol_core.market.brapi import BrapiProvider
from fincontrol_core.market.cache import InMemoryCache
from fincontrol_core.market.gateway import CachedMarketGateway
from fincontrol_core.market.yfinance_provider import YFinanceProvider
from fincontrol_persistence.core.unit_of_work import SqlAlchemyUnitOfWork
from fincontrol_worker.jobs import record_daily_snapshot_job, sync_bcb_and_benchmarks_job
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

UoWFactory = Callable[[], SqlAlchemyUnitOfWork]


def _xfail(finding: str, description: str):
    return pytest.mark.xfail(strict=True, raises=AssertionError, reason=f"{finding}: {description}")


class _OfflineTicker:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.info: dict[str, Any] = {}

    def history(self, period: str = "1y", interval: str = "1d") -> Any:
        import pandas as pd

        return pd.DataFrame()


def _gateway(bcb_handler: Callable[[httpx.Request], httpx.Response]) -> CachedMarketGateway:
    quote = {"results": [{"symbol": "ITUB4", "currency": "BRL", "regularMarketPrice": 35.0}]}
    return CachedMarketGateway(
        brapi=BrapiProvider(
            client=httpx.Client(
                transport=httpx.MockTransport(lambda _r: httpx.Response(200, json=quote))
            )
        ),
        yfinance=YFinanceProvider(ticker_factory=_OfflineTicker),
        bcb=BcbSgsProvider(client=httpx.Client(transport=httpx.MockTransport(bcb_handler))),
        cache=InMemoryCache(),
    )


@pytest.fixture
def uow_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> UoWFactory:
    db_url = f"sqlite:///{(tmp_path / 'audit_worker.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    persistence_dir = Path(__file__).resolve().parents[2] / "packages" / "persistence"
    alembic_cfg = Config(str(persistence_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(persistence_dir / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(db_url, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return lambda: SqlAlchemyUnitOfWork(session_factory=factory)


# ---------------------------------------------------------------------------
# I-03 — BCB history must cover the oldest fixed income position
# ---------------------------------------------------------------------------
def test_i03_bcb_sync_starts_at_oldest_fixed_income_issue(uow_factory: UoWFactory) -> None:
    issue = date(2022, 1, 3)
    with uow_factory() as uow:
        asset = uow.assets.add(
            AssetEntity(
                ticker="CDB-2022",
                name="CDB 2022",
                asset_type=AssetType.FIXED_INCOME,
                fixed_income_term=FixedIncomeTermEntity(
                    instrument_kind=FixedIncomeInstrumentKind.CDB,
                    indexer=FixedIncomeIndexer.CDI,
                    contracted_rate=Decimal("1.0"),
                    issue_date=issue,
                ),
            )
        )
        assert asset.id is not None
        uow.transactions.add(
            TransactionEntity(
                asset_id=asset.id,
                kind=TransactionKind.BUY,
                trade_date=issue,
                quantity=Decimal("1"),
                unit_price=Decimal("1000"),
            )
        )
        uow.commit()

    requested_starts: list[date] = []

    def bcb_handler(request: httpx.Request) -> httpx.Response:
        raw = request.url.params.get("dataInicial")
        requested_starts.append(datetime.strptime(raw, "%d/%m/%Y").date())
        return httpx.Response(200, json=[])

    sync_bcb_and_benchmarks_job(uow_factory, _gateway(bcb_handler), as_of_date=date(2025, 1, 6))

    assert requested_starts
    assert min(requested_starts) <= issue


# ---------------------------------------------------------------------------
# I-09 — Snapshot net flow must cover every trade since the previous snapshot
# ---------------------------------------------------------------------------
def test_i09_net_flow_includes_trades_since_previous_snapshot(uow_factory: UoWFactory) -> None:
    with uow_factory() as uow:
        uow.snapshots.upsert(
            PortfolioSnapshotEntity(
                snapshot_date=date(2025, 1, 1),
                invested_value=0.0,
                market_value=0.0,
                unrealized_pnl=0.0,
            )
        )
        asset = uow.assets.add(
            AssetEntity(ticker="ITUB4", name="Itau", asset_type=AssetType.STOCK_BR)
        )
        assert asset.id is not None
        # Worker was down on 2025-01-02, the day of the purchase.
        uow.transactions.add(
            TransactionEntity(
                asset_id=asset.id,
                kind=TransactionKind.BUY,
                trade_date=date(2025, 1, 2),
                quantity=Decimal("100"),
                unit_price=Decimal("32.00"),
            )
        )
        uow.commit()

    gateway = _gateway(lambda _r: httpx.Response(200, json=[]))
    snap = record_daily_snapshot_job(uow_factory, gateway, snapshot_date=date(2025, 1, 3))

    assert snap.net_flow == pytest.approx(3200.0)
