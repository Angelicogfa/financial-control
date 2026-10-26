"""Integration tests for FastAPI Controllers -> Handlers -> Services -> SqlAlchemyUnitOfWork."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import httpx
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


class _MockYFTicker:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.info: dict[str, Any] = {
            "regularMarketPrice": 5.15 if symbol == "USDBRL=X" else 560.0,
            "previousClose": 5.10 if symbol == "USDBRL=X" else 550.0,
            "currency": "BRL" if symbol == "USDBRL=X" else "USD",
            "longName": f"Mock {symbol}",
        }

    def history(self, period: str = "1y", interval: str = "1d") -> Any:
        import pandas as pd

        idx = pd.to_datetime(["2025-01-02", "2025-01-03"])
        return pd.DataFrame(
            {
                "Open": [100.0, 102.0],
                "High": [103.0, 106.0],
                "Low": [99.0, 101.0],
                "Close": [102.0, 105.0],
                "Volume": [1000.0, 1200.0],
            },
            index=idx,
        )


def _build_test_gateway() -> CachedMarketGateway:
    def brapi_mock(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "symbol": "WEGE3",
                        "longName": "WEG S.A.",
                        "currency": "BRL",
                        "regularMarketPrice": 54.0,
                        "priceEarnings": 30.0,
                        "earningsPerShare": 1.80,
                        "historicalDataPrice": [
                            {"date": "2025-01-02", "close": 50.0},
                            {"date": "2025-01-03", "close": 54.0},
                        ],
                        "defaultKeyStatistics": {
                            "priceToBook": {"raw": 7.5},
                            "bookValue": {"raw": 7.2},
                        },
                        "financialData": {
                            "returnOnEquity": {"raw": 0.28},
                            "profitMargins": {"raw": 0.18},
                        },
                        "summaryDetail": {
                            "dividendYield": {"raw": 0.025},
                            "trailingAnnualDividendRate": {"raw": 1.35},
                        },
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

    return CachedMarketGateway(
        brapi=BrapiProvider(client=httpx.Client(transport=httpx.MockTransport(brapi_mock))),
        yfinance=YFinanceProvider(ticker_factory=_MockYFTicker),
        bcb=BcbSgsProvider(client=httpx.Client(transport=httpx.MockTransport(bcb_mock))),
        cache=InMemoryCache(),
    )


def test_full_api_end_to_end_workflow(tmp_path: Path, monkeypatch) -> None:
    db_file = tmp_path / "api_integration.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    persistence_dir = Path(__file__).resolve().parents[3] / "packages" / "persistence"
    alembic_cfg = Config(str(persistence_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(persistence_dir / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(db_url, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    app = create_app()
    app.dependency_overrides[require_user] = lambda: "tester"
    test_gw = _build_test_gateway()
    app.dependency_overrides[get_uow_factory] = lambda: (
        lambda: SqlAlchemyUnitOfWork(session_factory=factory)
    )
    app.dependency_overrides[get_market_gateway] = lambda: test_gw

    client = TestClient(app)

    # 1. Health check
    r_health = client.get("/api/v1/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "ok"

    # 2. Create Stock Asset & Fixed Income Asset
    r_stock = client.post(
        "/api/v1/assets",
        json={
            "ticker": "WEGE3",
            "name": "WEG S.A.",
            "asset_type": "STOCK_BR",
            "use_cerrado": True,
            "cerrado_answers": {"governance": True, "perennial_sector": True},
        },
    )
    assert r_stock.status_code == 201
    stock_id = r_stock.json()["id"]

    r_rf = client.post(
        "/api/v1/assets",
        json={
            "ticker": "CDB-110",
            "name": "CDB Liquidez Diária 110% CDI",
            "asset_type": "FIXED_INCOME",
            "use_cerrado": False,
            "fixed_income_term": {
                "instrument_kind": "CDB",
                "indexer": "CDI",
                "contracted_rate": "1.10",
                "issue_date": "2024-06-01",
                "tax_exempt": False,
                "liquidity": "DAILY",
            },
        },
    )
    assert r_rf.status_code == 201
    rf_id = r_rf.json()["id"]

    # 3. Standardized Paginated Asset Listing
    r_list = client.get("/api/v1/assets?page=1&page_size=10&sort_by=ticker&sort_dir=asc")
    assert r_list.status_code == 200
    body_list = r_list.json()
    assert body_list["meta"]["total_items"] == 2
    assert len(body_list["items"]) == 2

    # 4. Toggle Cerrado off / set manual weight on stock
    r_cerrado = client.put(
        f"/api/v1/assets/{stock_id}/cerrado",
        json={
            "use_cerrado": False,
            "cerrado_answers": {"governance": True},
            "custom_class_weight": "100.0",
        },
    )
    assert r_cerrado.status_code == 200
    assert r_cerrado.json()["use_cerrado"] is False

    # 5. Create Transactions & Verify Short-Selling Rejection
    r_tx1 = client.post(
        "/api/v1/transactions",
        json={
            "asset_id": stock_id,
            "kind": "BUY",
            "trade_date": "2024-06-15",
            "quantity": "100",
            "unit_price": "40.00",
            "fees": "5.00",
        },
    )
    assert r_tx1.status_code == 201

    r_tx_short = client.post(
        "/api/v1/transactions",
        json={
            "asset_id": stock_id,
            "kind": "SELL",
            "trade_date": "2024-06-20",
            "quantity": "250",
            "unit_price": "45.00",
        },
    )
    assert r_tx_short.status_code == 400
    assert r_tx_short.json()["code"] == "INSUFFICIENT_QUANTITY"

    r_tx2 = client.post(
        "/api/v1/transactions",
        json={
            "asset_id": rf_id,
            "kind": "BUY",
            "trade_date": "2024-06-15",
            "quantity": "1",
            "unit_price": "5000.00",
        },
    )
    assert r_tx2.status_code == 201

    # 6. Record Earnings (Proventos)
    r_earn = client.post(
        "/api/v1/earnings",
        json={
            "asset_id": stock_id,
            "kind": "DIVIDEND",
            "payment_date": str(date.today()),
            "gross_amount": "180.00",
            "withholding_tax": "0.00",
        },
    )
    assert r_earn.status_code == 201

    r_earn_list = client.get("/api/v1/earnings?page=1&page_size=5")
    assert r_earn_list.status_code == 200
    assert r_earn_list.json()["meta"]["total_items"] == 1

    # 7. Portfolio & Consolidated Report
    r_port = client.get("/api/v1/portfolio/consolidated")
    assert r_port.status_code == 200
    port_data = r_port.json()
    assert port_data["total_invested_brl"] == 9005.00
    assert port_data["total_received_earnings_brl"] == 180.00
    assert port_data["total_consolidated_pnl_brl"] > 1500.00
    assert len(port_data["allocations"]) == 4

    # 8. Two-Level Contribution Simulator (with EQUAL_WEIGHT override)
    r_contrib = client.post(
        "/api/v1/portfolio/contribution",
        json={"amount_brl": 2000.0, "strategy_override": "EQUAL_WEIGHT"},
    )
    assert r_contrib.status_code == 200
    assert r_contrib.json()["contribution_amount_brl"] == 2000.0

    # 9. Single Asset Analysis & Portfolio Analytics
    r_analysis = client.get(f"/api/v1/assets/{stock_id}/analysis")
    assert r_analysis.status_code == 200
    analysis = r_analysis.json()
    graham = next(m for m in analysis["valuation"]["methods"] if m["method"] == "GRAHAM")
    assert graham["value"] is not None
    assert analysis["valuation"]["profile"] == "STOCK"
    assert analysis["checklist"]["profile"] == "STOCK"
    assert analysis["benchmark"] == "IBOV"

    r_analytics = client.get("/api/v1/portfolio/analytics")
    assert r_analytics.status_code == 200
    assert "summary" in r_analytics.json()

    # 10. ARCA Targets Settings GET & PUT
    r_targets = client.get("/api/v1/settings/arca-targets")
    assert r_targets.status_code == 200
    assert len(r_targets.json()) == 4

    r_update_targets = client.put(
        "/api/v1/settings/arca-targets",
        json={
            "targets": [
                {
                    "arca_class": "ACOES",
                    "target_pct": 30.0,
                    "intra_class_strategy": "EQUAL_WEIGHT",
                },
                {
                    "arca_class": "REAL_ESTATE",
                    "target_pct": 20.0,
                    "intra_class_strategy": "CERRADO",
                },
                {
                    "arca_class": "CAIXA",
                    "target_pct": 25.0,
                    "intra_class_strategy": "EQUAL_WEIGHT",
                },
                {
                    "arca_class": "ATIVOS_INTERNACIONAIS",
                    "target_pct": 25.0,
                    "intra_class_strategy": "MANUAL_WEIGHT",
                },
            ]
        },
    )
    assert r_update_targets.status_code == 200
    engine.dispose()
