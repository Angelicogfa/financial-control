"""Use cases (command/query handlers) for the research module.

Scope: B3 catalog screener and watchlist.
"""

from __future__ import annotations

from dataclasses import replace

from fincontrol_core.catalog.etf_exposure import suggest_arca_class
from fincontrol_core.domain.entities import AssetEntity
from fincontrol_core.domain.enums import (
    ArcaClass,
    AssetLifecycle,
    AssetType,
    Market,
)
from fincontrol_core.errors import ConflictError, NotFoundError, ValidationError
from fincontrol_core.market.batch import fetch_market_data
from fincontrol_core.policy.lifecycle import has_position
from fincontrol_core.ports.unit_of_work import AbstractUnitOfWork
from fincontrol_core.research.screener import ScreenerCriteria, screen

from fincontrol_api.core.deps import UoWFactory
from fincontrol_api.modules.portfolio.service import PortfolioApplicationService
from fincontrol_api.modules.research.schemas import (
    ScreenerResponseDTO,
    WatchlistAddRequest,
    WatchlistItemDTO,
)
from fincontrol_api.modules.research.serializers import to_screener_item_dto

WATCHLIST_STATUSES = frozenset({AssetLifecycle.WATCHLIST, AssetLifecycle.ELIGIBLE})


class ResearchHandler:
    """Find candidates in the catalog and follow them in the watchlist before buying."""

    def __init__(
        self, uow_factory: UoWFactory, portfolio_service: PortfolioApplicationService
    ) -> None:
        self.uow_factory = uow_factory
        self.portfolio_service = portfolio_service

    def screener(
        self, criteria: ScreenerCriteria, *, below_band: bool = False
    ) -> ScreenerResponseDTO:
        with self.uow_factory() as uow:
            if below_band:
                below = self.portfolio_service.classes_below_band(uow)
                criteria = replace(criteria, arca_classes=criteria.arca_classes | below)
                if not below:
                    return self._empty(uow, criteria)
            catalog = uow.catalog.list_all()
            assets = uow.assets.list_all(active_only=False)
            registered = {a.ticker: a for a in assets}
            by_id = self.portfolio_service.asset_lifecycles(uow, assets)
            lifecycles = {a.ticker: by_id[a.id][0] for a in assets if a.id in by_id}
            outcome = screen(
                catalog,
                criteria,
                load_fundamentals=self.portfolio_service.catalog_fundamentals,
                registered=registered,
                lifecycles=lifecycles,
                valuation_policy=self.portfolio_service.load_policy(uow).valuation,
            )
        return ScreenerResponseDTO(
            results=[to_screener_item_dto(r) for r in outcome.results],
            candidates=outcome.candidates,
            scanned=outcome.scanned,
            truncated=outcome.truncated,
            arca_classes=sorted(criteria.arca_classes),
            catalog_size=len(catalog),
            catalog_updated_at=max((c.updated_at for c in catalog if c.updated_at), default=None),
        )

    def _empty(self, uow: AbstractUnitOfWork, criteria: ScreenerCriteria) -> ScreenerResponseDTO:
        catalog = uow.catalog.list_all()
        return ScreenerResponseDTO(
            results=[],
            candidates=0,
            scanned=0,
            truncated=False,
            arca_classes=sorted(criteria.arca_classes),
            catalog_size=len(catalog),
            catalog_updated_at=max((c.updated_at for c in catalog if c.updated_at), default=None),
        )

    def watchlist(self) -> list[WatchlistItemDTO]:
        with self.uow_factory() as uow:
            assets = [
                a
                for a in uow.assets.list_all(active_only=True)
                if a.market not in (Market.MANUAL, Market.FIXED_INCOME_CURVE)
                and not has_position(a.transactions, fixed_income=False, events=a.corporate_events)
            ]
            return self._items(uow, assets)

    def add(self, req: WatchlistAddRequest) -> WatchlistItemDTO:
        ticker = req.ticker.strip().upper()
        with self.uow_factory() as uow:
            existing = uow.assets.get_by_ticker(ticker)
            if existing is not None and existing.is_active:
                raise ConflictError(f"{ticker} is already registered", code="ASSET_EXISTS")
            if existing is not None:
                asset = uow.assets.update(replace(existing, is_active=True))
            else:
                listed = uow.catalog.get(ticker)
                asset_type = req.asset_type or (listed.asset_type if listed else None)
                if asset_type is None:
                    raise ValidationError(
                        f"{ticker} is not in the catalog; inform asset_type",
                        code="UNKNOWN_INSTRUMENT",
                    )
                name = req.name or (listed.name if listed else ticker)
                asset = uow.assets.add(
                    AssetEntity(
                        ticker=ticker,
                        name=name,
                        asset_type=asset_type,
                        arca_class=suggest_arca_class(ticker, asset_type).arca_class,
                    )
                )
            uow.commit()
            reloaded = uow.assets.get_by_id(asset.id or 0) or asset
            return self._items(uow, [reloaded])[0]

    def remove(self, asset_id: int) -> None:
        with self.uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            if asset is None:
                raise NotFoundError(f"Asset id={asset_id} not found")
            if has_position(asset.transactions, fixed_income=asset.fixed_income_term is not None):
                raise ConflictError(
                    f"{asset.ticker} has an open position", code="ASSET_HAS_POSITION"
                )
            uow.assets.delete(asset_id, hard=not asset.transactions and not asset.earnings)
            uow.commit()

    def _items(self, uow: AbstractUnitOfWork, assets: list[AssetEntity]) -> list[WatchlistItemDTO]:
        service = self.portfolio_service
        market = fetch_market_data(
            service.gateway,
            assets,
            max_workers=service.fetch_workers,
            timeout_seconds=service.fetch_timeout_seconds,
        )
        histories = service.checklist_histories(uow, assets)
        lifecycles = service.asset_lifecycles(uow, assets)
        items: list[WatchlistItemDTO] = []
        for asset in assets:
            quote = market.quotes.get(asset.ticker)
            fund = market.fundamentals.get(asset.ticker)
            price = (
                quote.price
                if quote
                else (float(asset.manual_price) if asset.manual_price is not None else None)
            )
            evaluation = service.evaluate_with(asset, fund, histories.get(asset.ticker))
            valuation = service.value(uow, asset, price, fund)
            status, eligible = lifecycles.get(asset.id or 0, (AssetLifecycle.WATCHLIST, False))
            items.append(
                WatchlistItemDTO(
                    asset_id=asset.id or 0,
                    ticker=asset.ticker,
                    name=asset.name,
                    asset_type=asset.asset_type,
                    arca_class=asset.arca_class or ArcaClass.ACOES,
                    lifecycle_status=status,
                    eligible=eligible,
                    price=price,
                    change_pct=quote.change_pct if quote else None,
                    checklist_profile=asset.profile,
                    checklist_score=evaluation.score,
                    checklist_normalized_score=evaluation.normalized_score,
                    checklist_coverage_pct=round(evaluation.coverage_pct, 2),
                    checklist_recommendation=evaluation.recommendation.value,
                    valuation_verdict=valuation.verdict.value,
                    fair_value=valuation.fair_value,
                    margin=valuation.margin,
                )
            )
        return items


def parse_asset_types(values: list[str] | None) -> frozenset[AssetType]:
    return frozenset(AssetType(v) for v in values or [])
