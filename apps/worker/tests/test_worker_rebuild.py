"""Integration test for the post-fix reprocessing command (item 8.17)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from alembic import command
from alembic.config import Config
from fincontrol_core.domain.entities import AssetEntity, EarningEntity, TransactionEntity
from fincontrol_core.domain.enums import AssetType, EarningKind, TransactionKind
from fincontrol_core.market.bcb import BcbSgsProvider
from fincontrol_core.market.brapi import BrapiProvider
from fincontrol_core.market.cache import InMemoryCache
from fincontrol_core.market.gateway import CachedMarketGateway
from fincontrol_core.market.yfinance_provider import YFinanceProvider
from fincontrol_persistence.core.unit_of_work import SqlAlchemyUnitOfWork
from fincontrol_worker.rebuild import rebuild
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class _Ticker:
    """USDBRL=X at 5.0/5.5 and AAPL at 100/110 on Jan 2/3 2025."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.info: dict[str, Any] = {"regularMarketPrice": 5.5 if "BRL" in symbol else 110.0}

    def history(self, period: str = "1y", interval: str = "1d") -> Any:
        import pandas as pd

        closes = [5.0, 5.5] if "BRL" in self.symbol else [100.0, 110.0]
        return pd.DataFrame({"Close": closes}, index=pd.to_datetime(["2025-01-02", "2025-01-03"]))


def test_rebuild_reprices_usd_entries_and_rebuilds_snapshots(tmp_path: Path, monkeypatch) -> None:
    db_url = f"sqlite:///{(tmp_path / 'rebuild.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    persistence_dir = Path(__file__).resolve().parents[3] / "packages" / "persistence"
    cfg = Config(str(persistence_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(persistence_dir / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")
    factory = sessionmaker(bind=create_engine(db_url), expire_on_commit=False)

    def uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory=factory)

    with uow_factory() as uow:
        asset = uow.assets.add(
            AssetEntity(ticker="AAPL", name="Apple", asset_type=AssetType.STOCK_INTL)
        )
        assert asset.id is not None
        # Legacy rows recorded before FX became mandatory.
        uow.transactions.add(
            TransactionEntity(
                asset_id=asset.id,
                kind=TransactionKind.BUY,
                trade_date=date(2025, 1, 2),
                quantity=Decimal("10"),
                unit_price=Decimal("100"),
            )
        )
        uow.earnings.add(
            EarningEntity(
                asset_id=asset.id,
                kind=EarningKind.DIVIDEND,
                payment_date=date(2025, 1, 3),
                gross_amount=Decimal("2"),
            )
        )
        uow.commit()

    empty = httpx.MockTransport(lambda _r: httpx.Response(200, json=[]))
    gateway = CachedMarketGateway(
        brapi=BrapiProvider(client=httpx.Client(transport=empty)),
        yfinance=YFinanceProvider(ticker_factory=_Ticker),
        bcb=BcbSgsProvider(client=httpx.Client(transport=empty)),
        cache=InMemoryCache(),
    )

    report = rebuild(uow_factory, gateway)

    assert report.transactions_repriced == 1
    assert report.earnings_repriced == 1
    assert report.unpriced_entries == 0
    with uow_factory() as uow:
        loaded = uow.assets.get_by_ticker("AAPL")
        snapshots = {s.snapshot_date: s for s in uow.snapshots.list_range()}
    assert loaded is not None
    assert loaded.transactions[0].fx_rate == Decimal("5.0")
    assert loaded.earnings[0].fx_rate == Decimal("5.5")
    assert snapshots[date(2025, 1, 2)].invested_value == 5000.0
    assert snapshots[date(2025, 1, 3)].market_value == 10 * 110.0 * 5.5
    assert report.snapshots_written >= 2
