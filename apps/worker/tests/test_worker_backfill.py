"""Integration tests for incremental BCB sync and historical snapshot backfill (8.3, 8.9)."""

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
from fincontrol_core.domain.entities import AssetEntity, TransactionEntity
from fincontrol_core.domain.enums import AssetType, TransactionKind
from fincontrol_core.market.bcb import BcbSgsProvider
from fincontrol_core.market.brapi import BrapiProvider
from fincontrol_core.market.cache import InMemoryCache
from fincontrol_core.market.gateway import CachedMarketGateway
from fincontrol_core.market.yfinance_provider import YFinanceProvider
from fincontrol_persistence.unit_of_work import SqlAlchemyUnitOfWork
from fincontrol_worker.jobs import (
    backfill_snapshots_job,
    record_daily_snapshot_job,
    sync_bcb_and_benchmarks_job,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

UoWFactory = Callable[[], SqlAlchemyUnitOfWork]

ITUB4_CLOSES = {"2025-01-02": 30.0, "2025-01-03": 31.0, "2025-01-06": 32.0, "2025-01-07": 33.0}


class _IndexTicker:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.info: dict[str, Any] = {"regularMarketPrice": 5.5}

    def history(self, period: str = "1y", interval: str = "1d") -> Any:
        import pandas as pd

        idx = pd.to_datetime(list(ITUB4_CLOSES))
        return pd.DataFrame({"Close": [5.0, 5.1, 5.2, 5.3]}, index=idx)


@pytest.fixture
def uow_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> UoWFactory:
    db_url = f"sqlite:///{(tmp_path / 'backfill.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    persistence_dir = Path(__file__).resolve().parents[3] / "packages" / "persistence"
    cfg = Config(str(persistence_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(persistence_dir / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")
    engine = create_engine(db_url, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return lambda: SqlAlchemyUnitOfWork(session_factory=factory)


def _gateway(bcb_handler: Callable[[httpx.Request], httpx.Response]) -> CachedMarketGateway:
    history = [{"date": d, "close": c} for d, c in ITUB4_CLOSES.items()]
    payload = {
        "results": [{"symbol": "ITUB4", "regularMarketPrice": 33.0, "historicalDataPrice": history}]
    }
    return CachedMarketGateway(
        brapi=BrapiProvider(
            client=httpx.Client(
                transport=httpx.MockTransport(lambda _r: httpx.Response(200, json=payload))
            )
        ),
        yfinance=YFinanceProvider(ticker_factory=_IndexTicker),
        bcb=BcbSgsProvider(client=httpx.Client(transport=httpx.MockTransport(bcb_handler))),
        cache=InMemoryCache(),
    )


def _seed_stock(uow_factory: UoWFactory) -> None:
    with uow_factory() as uow:
        asset = uow.assets.add(
            AssetEntity(ticker="ITUB4", name="Itau", asset_type=AssetType.STOCK_BR)
        )
        assert asset.id is not None
        for on, qty in ((date(2025, 1, 2), "100"), (date(2025, 1, 6), "50")):
            uow.transactions.add(
                TransactionEntity(
                    asset_id=asset.id,
                    kind=TransactionKind.BUY,
                    trade_date=on,
                    quantity=Decimal(qty),
                    unit_price=Decimal("30"),
                )
            )
        uow.commit()


def test_backfill_values_each_business_day_with_historical_prices(uow_factory: UoWFactory) -> None:
    _seed_stock(uow_factory)
    gateway = _gateway(lambda _r: httpx.Response(200, json=[]))

    written = backfill_snapshots_job(uow_factory, gateway, end_date=date(2025, 1, 7))

    with uow_factory() as uow:
        snaps = {s.snapshot_date: s for s in uow.snapshots.list_range()}
    assert written == 4
    assert sorted(snaps) == [date(2025, 1, d) for d in (2, 3, 6, 7)]
    assert snaps[date(2025, 1, 3)].market_value == 3100.0
    assert snaps[date(2025, 1, 6)].market_value == 150 * 32.0
    assert snaps[date(2025, 1, 6)].net_flow == 1500.0
    assert snaps[date(2025, 1, 7)].net_flow == 0.0

    # A second run has nothing left to fill.
    assert backfill_snapshots_job(uow_factory, gateway, end_date=date(2025, 1, 7)) == 0


def test_daily_snapshot_is_skipped_on_holidays(uow_factory: UoWFactory) -> None:
    gateway = _gateway(lambda _r: httpx.Response(200, json=[]))
    assert record_daily_snapshot_job(uow_factory, gateway, snapshot_date=date(2025, 4, 21)) is None


def test_bcb_sync_only_requests_missing_windows(uow_factory: UoWFactory) -> None:
    _seed_stock(uow_factory)
    requests: list[tuple[str, date, date]] = []

    def bcb_handler(request: httpx.Request) -> httpx.Response:
        code = request.url.path.split("bcdata.sgs.")[1].split("/")[0]
        start = datetime.strptime(request.url.params["dataInicial"], "%d/%m/%Y").date()
        end = datetime.strptime(request.url.params["dataFinal"], "%d/%m/%Y").date()
        requests.append((code, start, end))
        rows = [{"data": d.strftime("%d/%m/%Y"), "valor": "0.05"} for d in (start, end)]
        return httpx.Response(200, json=rows)

    gateway = _gateway(bcb_handler)
    sync_bcb_and_benchmarks_job(uow_factory, gateway, as_of_date=date(2025, 1, 10))
    first_run = len(requests)
    requests.clear()

    sync_bcb_and_benchmarks_job(uow_factory, gateway, as_of_date=date(2025, 1, 20))

    assert first_run == 3
    cdi = [r for r in requests if r[0] == "12"]
    assert cdi == [("12", date(2025, 1, 11), date(2025, 1, 20))]


def test_series_coverage_fetches_early_gap_only_once(uow_factory: UoWFactory) -> None:
    from fincontrol_core.domain.enums import SeriesUnit
    from fincontrol_worker.jobs import ensure_series_coverage_job

    with uow_factory() as uow:
        for symbol in ("CDI", "SELIC"):
            uow.market_series.upsert_points(
                symbol, [(date(2024, 7, 1), 0.05)], unit=SeriesUnit.PERCENT_PER_DAY
            )
        uow.market_series.upsert_points(
            "IPCA", [(date(2024, 6, 1), 0.16)], unit=SeriesUnit.PERCENT_PER_MONTH
        )
        uow.commit()

    requests: list[tuple[str, date]] = []

    def bcb_handler(request: httpx.Request) -> httpx.Response:
        code = request.url.path.split("bcdata.sgs.")[1].split("/")[0]
        start = datetime.strptime(request.url.params["dataInicial"], "%d/%m/%Y").date()
        requests.append((code, start))
        return httpx.Response(200, json=[{"data": start.strftime("%d/%m/%Y"), "valor": "0.05"}])

    gateway = _gateway(bcb_handler)
    # The stored history already covers the default one-year window.
    assert ensure_series_coverage_job(uow_factory, gateway, as_of_date=date(2025, 6, 30)) == {}

    _seed_stock(uow_factory)  # trades from 2025-01-02 do not need more history
    with uow_factory() as uow:
        asset = uow.assets.get_by_ticker("ITUB4")
        assert asset is not None
        uow.transactions.add(
            TransactionEntity(
                asset_id=asset.id or 0,
                kind=TransactionKind.BUY,
                trade_date=date(2024, 3, 1),
                quantity=Decimal("1"),
                unit_price=Decimal("30"),
            )
        )
        uow.commit()

    counts = ensure_series_coverage_job(uow_factory, gateway, as_of_date=date(2025, 6, 30))

    assert counts["CDI"] >= 1
    assert ("12", date(2024, 3, 1)) in requests
    assert "IBOV" not in counts
    requests.clear()
    assert ensure_series_coverage_job(uow_factory, gateway, as_of_date=date(2025, 6, 30)) == {}
    assert requests == []
