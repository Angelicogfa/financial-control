"""Use cases for earnings (dividends, JCP, income)."""

from __future__ import annotations

from datetime import date

from controllers.ledger.requests import EarningCreateRequest, EarningUpdateRequest
from controllers.ledger.responses import EarningResponseDTO
from controllers.ledger.serializers import to_earning_dto
from controllers.shared.dependencies import UoWFactory
from controllers.shared.responses import PaginatedResponse
from controllers.shared.serializers import to_page_meta_dto
from core.errors import NotFoundError
from core.helpers.pagination import PaginationParams
from domain.accounts.services.use_cases import resolve_account_id
from domain.ledger.services.ledger import (
    require_fx_rate,
)
from domain.ledger.services.use_cases.common import require_asset
from domain.portfolio.services.snapshots import invalidate_snapshots_from
from domain.shared.entities import (
    EarningEntity,
)
from domain.shared.enums import (
    EarningKind,
)


class EarningHandler:
    """Application handler for Earnings (Proventos) commands and paginated queries."""

    def __init__(self, uow_factory: UoWFactory) -> None:
        self.uow_factory = uow_factory

    def list_paginated(
        self,
        params: PaginationParams,
        *,
        asset_id: int | None = None,
        kind: EarningKind | str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        account_id: int | None = None,
    ) -> PaginatedResponse[EarningResponseDTO]:
        with self.uow_factory() as uow:
            assets_map = {a.id: a.ticker for a in uow.assets.list_all(active_only=False)}
            kind_str = kind.value if isinstance(kind, EarningKind) else kind
            result = uow.earnings.list_paginated(
                params,
                asset_id=asset_id,
                kind=kind_str,
                date_from=date_from,
                date_to=date_to,
                account_id=account_id,
            )
            return PaginatedResponse(
                items=[to_earning_dto(e, ticker=assets_map.get(e.asset_id)) for e in result.items],
                meta=to_page_meta_dto(result.meta),
            )

    def create(self, req: EarningCreateRequest) -> EarningResponseDTO:
        with self.uow_factory() as uow:
            asset = require_asset(uow, req.asset_id)
            require_fx_rate(asset, req.fx_rate)
            entity = EarningEntity(
                asset_id=req.asset_id,
                kind=req.kind,
                payment_date=req.payment_date,
                gross_amount=req.gross_amount,
                withholding_tax=req.withholding_tax,
                net_amount=req.net_amount,
                ex_date=req.ex_date,
                notes=req.notes,
                fx_rate=req.fx_rate,
                account_id=resolve_account_id(uow, req.account_id),
            )
            saved = uow.earnings.add(entity)
            invalidate_snapshots_from(uow, saved.payment_date)
            uow.commit()
            return to_earning_dto(saved, ticker=asset.ticker)

    def get(self, earning_id: int) -> EarningResponseDTO:
        with self.uow_factory() as uow:
            earning = uow.earnings.get_by_id(earning_id)
            if earning is None:
                raise NotFoundError(f"Earning id={earning_id} not found")
            return to_earning_dto(earning, ticker=require_asset(uow, earning.asset_id).ticker)

    def update(self, earning_id: int, req: EarningUpdateRequest) -> EarningResponseDTO:
        with self.uow_factory() as uow:
            current = uow.earnings.get_by_id(earning_id)
            if current is None:
                raise NotFoundError(f"Earning id={earning_id} not found")
            asset = require_asset(uow, current.asset_id)
            require_fx_rate(asset, req.fx_rate)
            edited = EarningEntity(
                id=current.id,
                asset_id=current.asset_id,
                kind=req.kind,
                payment_date=req.payment_date,
                gross_amount=req.gross_amount,
                withholding_tax=req.withholding_tax,
                net_amount=req.net_amount,
                ex_date=req.ex_date,
                notes=req.notes,
                fx_rate=req.fx_rate,
                account_id=resolve_account_id(uow, req.account_id) or current.account_id,
                created_at=current.created_at,
            )
            saved = uow.earnings.update(edited)
            invalidate_snapshots_from(uow, current.payment_date, saved.payment_date)
            uow.commit()
            return to_earning_dto(saved, ticker=asset.ticker)

    def delete(self, earning_id: int) -> None:
        with self.uow_factory() as uow:
            current = uow.earnings.get_by_id(earning_id)
            if current is None or not uow.earnings.delete(earning_id):
                raise NotFoundError(f"Earning id={earning_id} not found")
            invalidate_snapshots_from(uow, current.payment_date)
            uow.commit()
