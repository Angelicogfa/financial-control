"""Use cases (command/query handlers) for the research module.

Scope: B3 catalog screener and watchlist.
"""

from __future__ import annotations

from dataclasses import replace

from controllers.research.requests import WatchlistAddRequest, WatchlistClassifyRequest
from controllers.research.responses import (
    ScreenerResponseDTO,
    TreasurySearchResponseDTO,
    WatchlistItemDTO,
)
from controllers.research.serializers import to_screener_item_dto, to_treasury_bond_dto
from controllers.shared.dependencies import UoWFactory
from core.errors import ConflictError, NotFoundError
from domain.market.entities import TreasuryBond
from domain.policy.services.lifecycle import has_position
from domain.portfolio.services.service import PortfolioApplicationService
from domain.research.services.screener import ScreenerCriteria, screen
from domain.research.services.service import register_researched_asset
from domain.shared.entities import AssetEntity
from domain.shared.enums import (
    ArcaClass,
    AssetLifecycle,
    AssetType,
    FixedIncomeIndexer,
    Market,
)
from domain.shared.unit_of_work import AbstractUnitOfWork
from infra.providers.batch import fetch_market_data

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

    def treasury(
        self,
        *,
        query: str | None = None,
        indexer: FixedIncomeIndexer | None = None,
        coupon_type: str | None = None,
    ) -> TreasurySearchResponseDTO:
        brapi_indexer = _BRAPI_INDEXER_BY_ENUM.get(indexer) if indexer is not None else None
        catalog_result = self.portfolio_service.gateway.list_treasury_bonds(
            indexer=brapi_indexer,
            coupon_type=coupon_type,
        )
        bonds = catalog_result.results
        if indexer is not None:
            bonds = [b for b in bonds if b.indexer == indexer]
        if coupon_type:
            bonds = [b for b in bonds if b.coupon_type == coupon_type.strip().lower()]
        if query and query.strip():
            needle = query.strip().casefold()
            bonds = [b for b in bonds if _matches_treasury_query(b, needle)]

        with self.uow_factory() as uow:
            treasury_assets = [
                a
                for a in uow.assets.list_all(active_only=True)
                if a.asset_type == AssetType.TREASURY
            ]
        return TreasurySearchResponseDTO(
            results=[
                to_treasury_bond_dto(b, asset_id=_matching_treasury_asset_id(b, treasury_assets))
                for b in bonds
            ],
            total=len(bonds),
            unavailable_reason=catalog_result.unavailable_reason,
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
                asset = uow.assets.update(
                    replace(
                        existing,
                        is_active=True,
                        arca_class=req.arca_class or existing.arca_class,
                    )
                )
            else:
                asset = register_researched_asset(
                    uow,
                    ticker,
                    asset_type=req.asset_type,
                    name=req.name,
                    arca_class=req.arca_class,
                )
            uow.commit()
            reloaded = uow.assets.get_by_id(asset.id or 0) or asset
            return self._items(uow, [reloaded])[0]

    def classify(self, asset_id: int, req: WatchlistClassifyRequest) -> WatchlistItemDTO:
        """Move a researched asset to another ARCA quadrant."""
        with self.uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            if asset is None or not asset.is_active:
                raise NotFoundError(f"Asset id={asset_id} not found")
            uow.assets.update(replace(asset, arca_class=req.arca_class))
            uow.commit()
            reloaded = uow.assets.get_by_id(asset_id) or asset
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


_BRAPI_INDEXER_BY_ENUM: dict[FixedIncomeIndexer, str] = {
    FixedIncomeIndexer.SELIC: "selic",
    FixedIncomeIndexer.PRE: "prefixado",
    FixedIncomeIndexer.IPCA: "ipca",
}


def _matches_treasury_query(bond: TreasuryBond, needle: str) -> bool:
    haystack = (
        bond.symbol.casefold(),
        bond.name.casefold(),
        bond.bond_type.casefold(),
        bond.maturity_date.isoformat(),
    )
    return any(needle in part for part in haystack)


def _matching_treasury_asset_id(bond: TreasuryBond, assets: list[AssetEntity]) -> int | None:
    for asset in assets:
        term = asset.fixed_income_term
        if (
            term is not None
            and term.instrument_kind == bond.instrument_kind
            and term.maturity_date == bond.maturity_date
        ):
            return asset.id
        if asset.name.strip().casefold() == bond.name.strip().casefold():
            return asset.id
    return None
