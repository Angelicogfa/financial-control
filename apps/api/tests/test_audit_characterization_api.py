"""Characterization tests for audit findings at the API/application-service boundary.

Same convention as packages/core/tests/test_audit_characterization.py: each test asserts
the correct behavior and stays `xfail(strict=True)` until its finding is fixed.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fincontrol_api.modules.portfolio.dependencies import get_portfolio_handler
from fincontrol_api.modules.portfolio.service import PortfolioApplicationService
from fincontrol_core.domain.entities import AssetEntity, MarketSeriesPoint, TransactionEntity
from fincontrol_core.domain.enums import AssetType, TransactionKind


def _xfail(finding: str, description: str):
    return pytest.mark.xfail(strict=True, raises=AssertionError, reason=f"{finding}: {description}")


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
def test_i04_deleting_buy_that_backs_a_sell_is_rejected(api: SimpleNamespace) -> None:
    asset_id = _create_stock(api.client)
    buy_id = _trade(api.client, asset_id, "BUY", "2025-01-02", "100")
    _trade(api.client, asset_id, "SELL", "2025-02-03", "50")

    resp = api.client.delete(f"/api/v1/transactions/{buy_id}")

    assert resp.status_code in (400, 409, 422)


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
def test_i05_internal_key_error_is_a_server_error(api: SimpleNamespace) -> None:
    def broken_report(**_kwargs: Any) -> Any:
        raise KeyError("missing_internal_field")

    api.app.dependency_overrides[get_portfolio_handler] = lambda: SimpleNamespace(
        get_portfolio_report=broken_report
    )
    client = TestClient(api.app, raise_server_exceptions=False)

    resp = client.get("/api/v1/portfolio")

    assert resp.status_code == 500
