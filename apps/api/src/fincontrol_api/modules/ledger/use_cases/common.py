"""Lookups shared by the ledger use cases."""

from __future__ import annotations

from fincontrol_core.domain.entities import (
    AssetEntity,
    TransactionEntity,
)
from fincontrol_core.errors import NotFoundError
from fincontrol_core.ports.unit_of_work import AbstractUnitOfWork


def require_asset(uow: AbstractUnitOfWork, asset_id: int) -> AssetEntity:
    asset = uow.assets.get_by_id(asset_id)
    if asset is None:
        raise NotFoundError(f"Asset id={asset_id} not found")
    return asset


def require_transaction(uow: AbstractUnitOfWork, tx_id: int) -> TransactionEntity:
    tx = uow.transactions.get_by_id(tx_id)
    if tx is None:
        raise NotFoundError(f"Transaction id={tx_id} not found")
    return tx
