"""ORM model <-> domain entity mappers.

Scope: transactions, earnings, corporate events and B3 import dedup.
"""

from __future__ import annotations

from decimal import Decimal

from domain.shared.entities import (
    CorporateEventEntity,
    EarningEntity,
    TransactionEntity,
)
from domain.shared.enums import (
    CorporateEventKind,
    EarningKind,
    TransactionKind,
)
from infra.data.models.ledger import CorporateEventModel, EarningModel, TransactionModel


def to_transaction_entity(model: TransactionModel) -> TransactionEntity:
    return TransactionEntity(
        id=model.id,
        asset_id=model.asset_id,
        kind=TransactionKind(model.kind),
        trade_date=model.trade_date,
        quantity=Decimal(model.quantity),
        unit_price=Decimal(model.unit_price),
        fees=Decimal(model.fees),
        fx_rate=Decimal(model.fx_rate),
        notes=model.notes,
        account_id=model.account_id,
        import_hash=model.import_hash,
        created_at=model.created_at,
    )


def to_earning_entity(model: EarningModel) -> EarningEntity:
    return EarningEntity(
        id=model.id,
        asset_id=model.asset_id,
        kind=EarningKind(model.kind),
        payment_date=model.payment_date,
        ex_date=model.ex_date,
        gross_amount=Decimal(model.gross_amount),
        withholding_tax=Decimal(model.withholding_tax),
        net_amount=Decimal(model.net_amount),
        fx_rate=Decimal(model.fx_rate),
        notes=model.notes,
        account_id=model.account_id,
        import_hash=model.import_hash,
        created_at=model.created_at,
    )


def to_corporate_event(model: CorporateEventModel) -> CorporateEventEntity:
    return CorporateEventEntity(
        id=model.id,
        asset_id=model.asset_id,
        kind=CorporateEventKind(model.kind),
        ex_date=model.ex_date,
        factor=Decimal(model.factor),
        unit_cost=Decimal(model.unit_cost or 0),
        notes=model.notes,
        import_hash=model.import_hash,
    )
