"""Weighted average cost position engine from buy and sell transactions."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from fincontrol_core.domain.entities import CorporateEventEntity, TransactionEntity
from fincontrol_core.domain.enums import CorporateEventKind, TransactionKind
from fincontrol_core.errors import ValidationError

ZERO = Decimal("0")
QUANTITY_STEP = Decimal("0.00000001")


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
    events: Iterable[CorporateEventEntity] = (),
    adjust_through: date | None = None,
) -> PositionState:
    """Consolidate buy and sell transactions using the weighted average price method.

    - Buy trades add `quantity * unit_price + fees` to `total_cost` and recalculate average price.
    - Sell trades do not change the average price; they realize P/L
      (`qty * (sell_price - avg) - fees`) and reduce `total_cost` proportionally.
    - On the same date, BUY trades are processed before SELL trades.
    - Corporate events apply at the start of their ex-date (item 12.4): the quantity is
      multiplied by the factor; bonus shares add `new shares x unit_cost` to the cost.
    - `adjust_through` expresses the quantity in the share terms of that later date (events
      after `up_to_date` up to it scale the quantity only), matching split-adjusted price
      series used to value past dates.
    """
    filtered = [tx for tx in transactions if up_to_date is None or tx.trade_date <= up_to_date]
    ordered = sorted(
        filtered,
        key=lambda t: (t.trade_date, t.kind != TransactionKind.BUY, t.id or 0),
    )
    all_events = sorted(events, key=lambda e: (e.ex_date, e.id or 0))
    pending = [e for e in all_events if up_to_date is None or e.ex_date <= up_to_date]

    quantity = ZERO
    total_cost = ZERO
    total_cost_brl = ZERO
    realized = ZERO
    realized_brl = ZERO

    def apply(event: CorporateEventEntity) -> None:
        nonlocal quantity, total_cost, total_cost_brl
        if quantity <= ZERO:
            return
        if event.kind == CorporateEventKind.BONUS:
            new_shares = quantity * (event.factor - 1)
            total_cost += new_shares * event.unit_cost
            total_cost_brl += new_shares * event.unit_cost
        quantity = (quantity * event.factor).quantize(QUANTITY_STEP)

    for tx in ordered:
        while pending and pending[0].ex_date <= tx.trade_date:
            apply(pending.pop(0))
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

    for event in pending:
        apply(event)
    if adjust_through is not None and up_to_date is not None:
        for event in all_events:
            if up_to_date < event.ex_date <= adjust_through and quantity > ZERO:
                quantity = (quantity * event.factor).quantize(QUANTITY_STEP)

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
