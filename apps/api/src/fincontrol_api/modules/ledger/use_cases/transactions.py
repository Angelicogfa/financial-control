"""Use cases for buy/sell transactions."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from fincontrol_core.domain.entities import (
    AssetEntity,
    TransactionEntity,
)
from fincontrol_core.domain.pagination import PaginationParams
from fincontrol_core.portfolio.fixed_income import RateCurves
from fincontrol_core.portfolio.ledger import (
    require_fx_rate,
    validate_ledger,
    validate_ledger_change,
)
from fincontrol_core.ports.unit_of_work import AbstractUnitOfWork

from fincontrol_api.core.deps import UoWFactory
from fincontrol_api.modules.accounts.use_cases import resolve_account_id
from fincontrol_api.modules.ledger.schemas import (
    TransactionCreateRequest,
    TransactionResponseDTO,
    TransactionUpdateRequest,
)
from fincontrol_api.modules.ledger.serializers import to_transaction_dto
from fincontrol_api.modules.ledger.use_cases.common import require_asset, require_transaction
from fincontrol_api.modules.portfolio.service import PortfolioApplicationService
from fincontrol_api.modules.shared.schemas import PaginatedResponse
from fincontrol_api.modules.shared.serializers import to_page_meta_dto


class TransactionHandler:
    """Application handler for buy/sell Transaction commands and paginated queries.

    Every command validates the whole resulting ledger of the asset (finding I-04).
    """

    def __init__(
        self, uow_factory: UoWFactory, portfolio_service: PortfolioApplicationService
    ) -> None:
        self.uow_factory = uow_factory
        self.portfolio_service = portfolio_service

    def list_paginated(
        self,
        params: PaginationParams,
        *,
        asset_id: int | None = None,
        kind: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        account_id: int | None = None,
    ) -> PaginatedResponse[TransactionResponseDTO]:
        with self.uow_factory() as uow:
            assets_map = {a.id: a.ticker for a in uow.assets.list_all(active_only=False)}
            result = uow.transactions.list_paginated(
                params,
                asset_id=asset_id,
                kind=kind,
                date_from=date_from,
                date_to=date_to,
                account_id=account_id,
            )
            return PaginatedResponse(
                items=[
                    to_transaction_dto(t, ticker=assets_map.get(t.asset_id)) for t in result.items
                ],
                meta=to_page_meta_dto(result.meta),
            )

    def _curves(
        self, uow: AbstractUnitOfWork, asset: AssetEntity, entries: list[TransactionEntity]
    ) -> RateCurves | None:
        as_of = max((t.trade_date for t in entries), default=date.today())
        return self.portfolio_service.ledger_curves(uow, asset, as_of)

    def get(self, tx_id: int) -> TransactionResponseDTO:
        with self.uow_factory() as uow:
            tx = require_transaction(uow, tx_id)
            return to_transaction_dto(tx, ticker=require_asset(uow, tx.asset_id).ticker)

    def create(self, req: TransactionCreateRequest) -> TransactionResponseDTO:
        with self.uow_factory() as uow:
            asset = require_asset(uow, req.asset_id)
            require_fx_rate(asset, req.fx_rate)
            candidate = TransactionEntity(
                asset_id=req.asset_id,
                kind=req.kind,
                trade_date=req.trade_date,
                quantity=req.quantity,
                unit_price=req.unit_price,
                fees=req.fees,
                fx_rate=req.fx_rate,
                notes=req.notes,
                account_id=resolve_account_id(uow, req.account_id),
            )
            entries = [*asset.transactions, candidate]
            validate_ledger(asset, entries, curves=self._curves(uow, asset, entries))

            saved = uow.transactions.add(candidate)
            uow.commit()
            return to_transaction_dto(saved, ticker=asset.ticker)

    def update(self, tx_id: int, req: TransactionUpdateRequest) -> TransactionResponseDTO:
        with self.uow_factory() as uow:
            current = require_transaction(uow, tx_id)
            asset = require_asset(uow, current.asset_id)
            require_fx_rate(asset, req.fx_rate)
            edited = replace(
                current,
                kind=req.kind,
                trade_date=req.trade_date,
                quantity=req.quantity,
                unit_price=req.unit_price,
                fees=req.fees,
                fx_rate=req.fx_rate,
                notes=req.notes,
                account_id=resolve_account_id(uow, req.account_id) or current.account_id,
            )
            entries = [edited if t.id == tx_id else t for t in asset.transactions]
            validate_ledger_change(asset, entries, curves=self._curves(uow, asset, entries))

            saved = uow.transactions.update(edited)
            uow.commit()
            return to_transaction_dto(saved, ticker=asset.ticker)

    def delete(self, tx_id: int) -> None:
        with self.uow_factory() as uow:
            current = require_transaction(uow, tx_id)
            asset = require_asset(uow, current.asset_id)
            entries = [t for t in asset.transactions if t.id != tx_id]
            validate_ledger_change(asset, entries, curves=self._curves(uow, asset, entries))

            uow.transactions.delete(tx_id)
            uow.commit()
