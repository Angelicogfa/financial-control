"""Ledger integrity rules applied before any transaction is created, edited or deleted (I-04)."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from fincontrol_core.domain.entities import AssetEntity, TransactionEntity
from fincontrol_core.errors import ConflictError, ValidationError
from fincontrol_core.portfolio.fixed_income import RateCurves, value_fixed_income_position
from fincontrol_core.portfolio.positions import InsufficientQuantityError, build_position


class LedgerConflictError(ConflictError):
    """Removing or changing an entry would leave later entries without backing."""

    code = "LEDGER_CONFLICT"


def require_fx_rate(asset: AssetEntity, fx_rate: Decimal) -> None:
    """Foreign-currency assets must record the FX of the trade or payment (finding C-02)."""
    if (asset.currency or "BRL").upper() != "BRL" and fx_rate == Decimal("1"):
        raise ValidationError(
            f"{asset.ticker} trades in {asset.currency}: inform the {asset.currency}/BRL "
            "rate of the date (fx_rate)",
            code="FX_RATE_REQUIRED",
        )


def validate_ledger(
    asset: AssetEntity,
    transactions: Iterable[TransactionEntity],
    *,
    curves: RateCurves | None = None,
) -> None:
    """Raise `InsufficientQuantityError` if the ledger sells more than it holds at any date."""
    entries = list(transactions)
    if not entries:
        return
    if asset.fixed_income_term is not None:
        last_date = max(t.trade_date for t in entries)
        value_fixed_income_position(entries, asset.fixed_income_term, last_date, curves=curves)
    else:
        build_position(entries)


def validate_ledger_change(
    asset: AssetEntity,
    transactions: Iterable[TransactionEntity],
    *,
    curves: RateCurves | None = None,
) -> None:
    """Validate a ledger after removing/editing an entry, reporting breakage as a conflict."""
    try:
        validate_ledger(asset, transactions, curves=curves)
    except InsufficientQuantityError as err:
        raise LedgerConflictError(
            f"This change would leave {asset.ticker} with an invalid ledger: {err}"
        ) from err
