"""Characterization tests for audit findings at the API/application-service boundary.

Same convention as packages/core/tests/test_audit_characterization.py: each test asserts
the correct behavior and stays `xfail(strict=True)` until its finding is fixed.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from fincontrol_api.dependencies import (
    get_market_gateway,
    get_portfolio_handler,
    get_uow_factory,
)
from fincontrol_api.main import create_app
from fincontrol_api.services.portfolio_service import PortfolioApplicationService
from fincontrol_core.domain.entities import AssetEntity, MarketSeriesPoint, TransactionEntity
from fincontrol_core.domain.enums import AssetType, TransactionKind
from fincontrol_core.market.bcb import BcbSgsProvider
from fincontrol_core.market.brapi import BrapiProvider
from fincontrol_core.market.cache import InMemoryCache
from fincontrol_core.market.gateway import CachedMarketGateway
from fincontrol_core.market.yfinance_provider import YFinanceProvider
from fincontrol_persistence.unit_of_work import SqlAlchemyUnitOfWork
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _xfail(finding: str, description: str):
    return pytest.mark.xfail(strict=True, raises=AssertionError, reason=f"{finding}: {description}")


class _OfflineTicker:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.info: dict[str, Any] = {}

    def history(self, period: str = "1y", interval: str = "1d") -> Any:
        import pandas as pd

        return pd.DataFrame()


def _offline_gateway() -> CachedMarketGateway:
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
    db_url = f"sqlite:///{(tmp_path / 'audit_api.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    persistence_dir = Path(__file__).resolve().parents[3] / "packages" / "persistence"
    alembic_cfg = Config(str(persistence_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(persistence_dir / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(db_url, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory=factory)

    app = create_app()
    gateway = _offline_gateway()
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    app.dependency_overrides[get_market_gateway] = lambda: gateway

    yield SimpleNamespace(app=app, client=TestClient(app), uow_factory=uow_factory)
    engine.dispose()


def _create_stock(client: TestClient, ticker: str = "WEGE3") -> int:
    resp = client.post(
        "/api/v1/assets",
        json={"ticker": ticker, "name": ticker, "asset_type": "STOCK_BR"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _trade(client: TestClient, asset_id: int, kind: str, on: str, qty: str) -> int:
    resp = client.post(
        "/api/v1/transactions",
        json={
            "asset_id": asset_id,
            "kind": kind,
            "trade_date": on,
            "quantity": qty,
            "unit_price": "40.00",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# C-03 — Analytics must never present a benchmark as the user's portfolio
# ---------------------------------------------------------------------------
@_xfail("C-03", "with < 2 snapshots the IBOV return series is labelled PORTFOLIO")
def test_c03_analytics_without_history_does_not_fabricate_portfolio_curve() -> None:
    ibov = [
        MarketSeriesPoint("IBOV", date(2025, 1, 2), 120_000.0),
        MarketSeriesPoint("IBOV", date(2025, 1, 3), 121_000.0),
        MarketSeriesPoint("IBOV", date(2025, 1, 6), 119_500.0),
    ]
    uow = SimpleNamespace(
        snapshots=SimpleNamespace(list_range=lambda **_kw: []),
        market_series=SimpleNamespace(
            list_series=lambda symbol, **_kw: ibov if symbol == "IBOV" else []
        ),
    )
    gateway = SimpleNamespace(get_macro_rates=lambda: (0.149, 0.046))
    service = PortfolioApplicationService(gateway=gateway)  # type: ignore[arg-type]

    result = service.build_portfolio_analytics(
        uow,  # type: ignore[arg-type]
        date_from=date(2025, 1, 1),
        date_to=date(2025, 1, 31),
    )

    assert "PORTFOLIO" not in result["curves"]
    assert result["summary"].observations == 0


# ---------------------------------------------------------------------------
# I-02 — contracted_rate must follow ADR 0006 (fraction / multiplier), not be guessed
# ---------------------------------------------------------------------------
@_xfail("I-02", "API accepts percent-scaled contracted rates and guesses the scale later")
@pytest.mark.parametrize(
    ("indexer", "rate"),
    [("IPCA", "6.5"), ("CDI", "110.0")],
)
def test_i02_percent_scaled_contracted_rate_is_rejected(
    api: SimpleNamespace, indexer: str, rate: str
) -> None:
    resp = api.client.post(
        "/api/v1/assets",
        json={
            "ticker": f"CDB-{indexer}",
            "name": f"CDB {indexer}",
            "asset_type": "FIXED_INCOME",
            "fixed_income_term": {
                "instrument_kind": "CDB",
                "indexer": indexer,
                "contracted_rate": rate,
                "issue_date": "2025-01-02",
            },
        },
    )
    assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# I-04 — Ledger integrity
# ---------------------------------------------------------------------------
@_xfail("I-04", "deleting a BUY does not revalidate later SELLs")
def test_i04_deleting_buy_that_backs_a_sell_is_rejected(api: SimpleNamespace) -> None:
    asset_id = _create_stock(api.client)
    buy_id = _trade(api.client, asset_id, "BUY", "2025-01-02", "100")
    _trade(api.client, asset_id, "SELL", "2025-02-03", "50")

    resp = api.client.delete(f"/api/v1/transactions/{buy_id}")

    assert resp.status_code in (400, 409, 422)


@_xfail("I-04", "one invalid ledger turns the whole portfolio endpoint into HTTP 400")
def test_i04_invalid_ledger_does_not_break_portfolio(api: SimpleNamespace) -> None:
    _create_stock(api.client, "WEGE3")
    with api.uow_factory() as uow:
        broken = uow.assets.add(
            AssetEntity(ticker="PETR4", name="Petrobras", asset_type=AssetType.STOCK_BR)
        )
        assert broken.id is not None
        uow.transactions.add(
            TransactionEntity(
                asset_id=broken.id,
                kind=TransactionKind.SELL,
                trade_date=date(2025, 1, 2),
                quantity=Decimal("10"),
                unit_price=Decimal("30"),
            )
        )
        uow.commit()

    resp = api.client.get("/api/v1/portfolio")

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# I-05 — Unexpected errors must surface as 500, not as 404/400
# ---------------------------------------------------------------------------
@_xfail("I-05", "KeyError is a LookupError and is translated into HTTP 404")
def test_i05_internal_key_error_is_a_server_error(api: SimpleNamespace) -> None:
    def broken_report(**_kwargs: Any) -> Any:
        raise KeyError("missing_internal_field")

    api.app.dependency_overrides[get_portfolio_handler] = lambda: SimpleNamespace(
        get_portfolio_report=broken_report
    )
    client = TestClient(api.app, raise_server_exceptions=False)

    resp = client.get("/api/v1/portfolio")

    assert resp.status_code == 500
