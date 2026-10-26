"""Shared API test fixtures: migrated SQLite database and an offline market gateway."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from fincontrol_api.composition import get_market_gateway, get_uow_factory
from fincontrol_api.main import create_app
from fincontrol_api.modules.auth.dependencies import require_user
from fincontrol_core.market.bcb import BcbSgsProvider
from fincontrol_core.market.brapi import BrapiProvider
from fincontrol_core.market.cache import InMemoryCache
from fincontrol_core.market.gateway import CachedMarketGateway
from fincontrol_core.market.yfinance_provider import YFinanceProvider
from fincontrol_persistence.core.unit_of_work import SqlAlchemyUnitOfWork
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class _OfflineTicker:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.info: dict[str, Any] = {}

    def history(self, period: str = "1y", interval: str = "1d") -> Any:
        import pandas as pd

        return pd.DataFrame()


def offline_gateway() -> CachedMarketGateway:
    """Gateway whose providers return no data (quotes fall back, BCB uses annual rates)."""
    empty_brapi = httpx.MockTransport(lambda _r: httpx.Response(200, json={"results": []}))
    empty_bcb = httpx.MockTransport(lambda _r: httpx.Response(200, json=[]))
    return CachedMarketGateway(
        brapi=BrapiProvider(client=httpx.Client(transport=empty_brapi)),
        yfinance=YFinanceProvider(ticker_factory=_OfflineTicker),
        bcb=BcbSgsProvider(client=httpx.Client(transport=empty_bcb)),
        cache=InMemoryCache(),
    )


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    """FastAPI app wired to a freshly migrated SQLite database and an offline gateway."""
    db_url = f"sqlite:///{(tmp_path / 'api.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    persistence_dir = Path(__file__).resolve().parents[2] / "packages" / "persistence"
    alembic_cfg = Config(str(persistence_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(persistence_dir / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(db_url, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory=factory)

    app = create_app()
    gateway = offline_gateway()
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    app.dependency_overrides[get_market_gateway] = lambda: gateway
    app.dependency_overrides[require_user] = lambda: "tester"

    yield SimpleNamespace(app=app, client=TestClient(app), uow_factory=uow_factory)
    engine.dispose()
