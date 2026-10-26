"""Unit tests for ledger integrity rules (finding I-04) and FX requirements (finding C-02)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from core.errors import ValidationError
from domain.ledger.services.ledger import (
    LedgerConflictError,
    require_fx_rate,
    validate_ledger,
    validate_ledger_change,
)
from domain.portfolio.services.positions import InsufficientQuantityError
from domain.shared.entities import AssetEntity, TransactionEntity
from domain.shared.enums import AssetType, TransactionKind

STOCK = AssetEntity(id=1, ticker="WEGE3", name="WEG", asset_type=AssetType.STOCK_BR)
USD_STOCK = AssetEntity(id=2, ticker="AAPL", name="Apple", asset_type=AssetType.STOCK_INTL)


def _tx(kind: TransactionKind, on: date, qty: str) -> TransactionEntity:
    return TransactionEntity(
        asset_id=1, kind=kind, trade_date=on, quantity=Decimal(qty), unit_price=Decimal("10")
    )


def test_validate_ledger_accepts_empty_and_consistent_ledgers() -> None:
    validate_ledger(STOCK, [])
    validate_ledger(
        STOCK,
        [
            _tx(TransactionKind.BUY, date(2025, 1, 2), "10"),
            _tx(TransactionKind.SELL, date(2025, 1, 3), "10"),
        ],
    )


def test_validate_ledger_rejects_oversell_as_validation_error() -> None:
    with pytest.raises(InsufficientQuantityError):
        validate_ledger(STOCK, [_tx(TransactionKind.SELL, date(2025, 1, 3), "1")])


def test_validate_ledger_change_reports_conflict() -> None:
    with pytest.raises(LedgerConflictError, match="invalid ledger") as err:
        validate_ledger_change(STOCK, [_tx(TransactionKind.SELL, date(2025, 1, 3), "1")])
    assert err.value.code == "LEDGER_CONFLICT"


def test_require_fx_rate_only_for_foreign_currency_assets() -> None:
    require_fx_rate(STOCK, Decimal("1"))
    require_fx_rate(USD_STOCK, Decimal("5.4"))
    with pytest.raises(ValidationError) as err:
        require_fx_rate(USD_STOCK, Decimal("1"))
    assert err.value.code == "FX_RATE_REQUIRED"
