"""Use cases for corporate events (splits, groupings)."""

from __future__ import annotations

from controllers.ledger.requests import CorporateEventRequest
from controllers.ledger.responses import CorporateEventDTO
from controllers.shared.dependencies import UoWFactory
from core.errors import NotFoundError, ValidationError
from domain.ledger.services.ledger import validate_ledger_change
from domain.shared.entities import AssetEntity, CorporateEventEntity
from domain.shared.unit_of_work import AbstractUnitOfWork


def to_event_dto(event: CorporateEventEntity, ticker: str | None) -> CorporateEventDTO:
    return CorporateEventDTO(
        id=event.id or 0,
        asset_id=event.asset_id,
        ticker=ticker,
        kind=event.kind,
        ex_date=event.ex_date,
        factor=event.factor,
        unit_cost=event.unit_cost,
        notes=event.notes,
        imported=event.import_hash is not None,
    )


class CorporateEventHandler:
    """Every change revalidates the asset's ledger with the resulting event list."""

    def __init__(self, uow_factory: UoWFactory) -> None:
        self.uow_factory = uow_factory

    def list_all(self, *, asset_id: int | None = None) -> list[CorporateEventDTO]:
        with self.uow_factory() as uow:
            tickers = {a.id: a.ticker for a in uow.assets.list_all(active_only=False)}
            return [
                to_event_dto(e, tickers.get(e.asset_id))
                for e in uow.corporate_events.list_all(asset_id=asset_id)
            ]

    def create(self, req: CorporateEventRequest) -> CorporateEventDTO:
        with self.uow_factory() as uow:
            asset = _market_asset(uow, req.asset_id)
            event = CorporateEventEntity(
                asset_id=req.asset_id,
                kind=req.kind,
                ex_date=req.ex_date,
                factor=req.factor,
                unit_cost=req.unit_cost,
                notes=req.notes,
            )
            validate_ledger_change(
                asset, asset.transactions, events=[*asset.corporate_events, event]
            )
            saved = uow.corporate_events.add(event)
            uow.commit()
            return to_event_dto(saved, asset.ticker)

    def delete(self, event_id: int) -> None:
        with self.uow_factory() as uow:
            event = uow.corporate_events.get(event_id)
            if event is None:
                raise NotFoundError(f"Corporate event id={event_id} not found")
            asset = _market_asset(uow, event.asset_id)
            remaining = [e for e in asset.corporate_events if e.id != event_id]
            validate_ledger_change(asset, asset.transactions, events=remaining)
            uow.corporate_events.delete(event_id)
            uow.commit()


def _market_asset(uow: AbstractUnitOfWork, asset_id: int) -> AssetEntity:
    asset = uow.assets.get_by_id(asset_id)
    if asset is None:
        raise NotFoundError(f"Asset id={asset_id} not found")
    if asset.fixed_income_term is not None:
        raise ValidationError(
            "Corporate events apply to shares and fund quotas, not fixed income",
            code="EVENT_NOT_APPLICABLE",
        )
    return asset
