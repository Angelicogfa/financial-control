"""Domain entity to DTO serializers for the ledger module.

Scope: transactions, earnings, corporate events and B3 statement imports.
"""

from __future__ import annotations

from controllers.ledger.responses import EarningResponseDTO, TransactionResponseDTO
from domain.shared.entities import (
    EarningEntity,
    TransactionEntity,
)


def to_transaction_dto(
    entity: TransactionEntity, ticker: str | None = None
) -> TransactionResponseDTO:
    qty = float(entity.quantity)
    price = float(entity.unit_price)
    fees = float(entity.fees)
    fx = float(entity.fx_rate)
    total_brl = round((qty * price + fees) * fx, 2)
    return TransactionResponseDTO(
        id=entity.id or 0,
        asset_id=entity.asset_id,
        ticker=ticker,
        kind=entity.kind,
        trade_date=entity.trade_date,
        quantity=qty,
        unit_price=price,
        fees=fees,
        fx_rate=fx,
        total_brl=total_brl,
        notes=entity.notes,
        account_id=entity.account_id,
        created_at=entity.created_at,
    )


def to_earning_dto(entity: EarningEntity, ticker: str | None = None) -> EarningResponseDTO:
    gross = float(entity.gross_amount)
    tax = float(entity.withholding_tax)
    net = float(entity.net_amount) if entity.net_amount is not None else (gross - tax)
    fx = float(entity.fx_rate)
    return EarningResponseDTO(
        id=entity.id or 0,
        asset_id=entity.asset_id,
        ticker=ticker,
        kind=entity.kind,
        payment_date=entity.payment_date,
        ex_date=entity.ex_date,
        gross_amount=gross,
        withholding_tax=tax,
        net_amount=net,
        fx_rate=fx,
        net_amount_brl=round(net * fx, 2),
        notes=entity.notes,
        account_id=entity.account_id,
        created_at=entity.created_at,
    )
