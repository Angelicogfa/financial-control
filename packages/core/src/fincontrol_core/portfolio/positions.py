"""Weighted average cost position engine from buy and sell transactions."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from fincontrol_core.domain.entities import TransactionEntity
from fincontrol_core.domain.enums import TransactionKind
from fincontrol_core.errors import ValidationError

ZERO = Decimal("0")


class InsufficientQuantityError(ValidationError):
    """Raised when a sell transaction exceeds the currently held quantity."""

    code = "INSUFFICIENT_QUANTITY"


@dataclass(frozen=True)
class PositionState:
    """Aggregated position state for a single asset."""

    quantity: Decimal = ZERO
    average_price: Decimal = ZERO
    total_cost: Decimal = ZERO
    total_cost_brl: Decimal = ZERO
    realized_pnl: Decimal = ZERO
    realized_pnl_brl: Decimal = ZERO

    @property
    def is_open(self) -> bool:
        return self.quantity > ZERO


def build_position(
    transactions: Iterable[TransactionEntity],
    *,
    up_to_date: date | None = None,
) -> PositionState:
    """Consolidate buy and sell transactions using the weighted average price method.

    - Buy trades add `quantity * unit_price + fees` to `total_cost` and recalculate average price.
    - Sell trades do not change the average price; they realize P/L
      (`qty * (sell_price - avg) - fees`) and reduce `total_cost` proportionally.
    - On the same date, BUY trades are processed before SELL trades.
    """
    filtered = [
        tx for tx in transactions if up_to_date is None or tx.trade_date <= up_to_date
    ]
    ordered = sorted(
        filtered,
        key=lambda t: (t.trade_date, t.kind != TransactionKind.BUY, t.id or 0),
    )

    quantity = ZERO
    total_cost = ZERO
    total_cost_brl = ZERO
    realized = ZERO
    realized_brl = ZERO

    for tx in ordered:
        fx = tx.fx_rate if tx.fx_rate > ZERO else Decimal("1")
        if tx.kind == TransactionKind.BUY:
            lot_cost = tx.quantity * tx.unit_price + tx.fees
            total_cost += lot_cost
            total_cost_brl += lot_cost * fx
            quantity += tx.quantity
        else:
            if tx.quantity > quantity:
                raise InsufficientQuantityError(
                    f"Cannot sell {tx.quantity} on {tx.trade_date}; held quantity is {quantity}"
                )
            avg_price = total_cost / quantity
            avg_cost_brl = total_cost_brl / quantity
            trade_pnl = tx.quantity * (tx.unit_price - avg_price) - tx.fees
            trade_pnl_brl = tx.quantity * (tx.unit_price * fx - avg_cost_brl) - (tx.fees * fx)
            realized += trade_pnl
            realized_brl += trade_pnl_brl
            total_cost -= tx.quantity * avg_price
            total_cost_brl -= tx.quantity * avg_cost_brl
            quantity -= tx.quantity
            if quantity == ZERO:
                total_cost = ZERO
                total_cost_brl = ZERO

    average_price = total_cost / quantity if quantity > ZERO else ZERO
    return PositionState(
        quantity=quantity,
        average_price=average_price,
        total_cost=total_cost,
        total_cost_brl=total_cost_brl,
        realized_pnl=realized,
        realized_pnl_brl=realized_brl,
    )


def quantity_on(
    transactions: Iterable[TransactionEntity],
    asset_id: int,
    on_date: date,
) -> Decimal:
    """Return the held quantity of a specific asset at the end of `on_date`."""
    qty = ZERO
    for tx in transactions:
        if tx.asset_id != asset_id or tx.trade_date > on_date:
            continue
        qty += tx.quantity if tx.kind == TransactionKind.BUY else -tx.quantity
    return qty
