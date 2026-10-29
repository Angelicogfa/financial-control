"""Use cases (command/query handlers) for the research module.

Scope: B3 catalog screener and watchlist.
"""

from __future__ import annotations

import logging
from dataclasses import replace

from controllers.research.requests import WatchlistAddRequest, WatchlistClassifyRequest
from controllers.research.responses import (
    AssetComparisonDTO,
    ScreenerResponseDTO,
    TreasurySearchResponseDTO,
    WatchlistItemDTO,
)
from controllers.research.serializers import (
    to_asset_comparison_dto,
    to_screener_item_dto,
    to_treasury_bond_dto,
)
from controllers.shared.dependencies import UoWFactory
from core.errors import ConflictError, NotFoundError, ValidationError
from domain.assets.services.history import historical_metrics
from domain.market.entities import TreasuryBond
from domain.policy.services.lifecycle import has_position
from domain.portfolio.services.service import PortfolioApplicationService
from domain.research.services.comparison import (
    ComparedAsset,
    compare_assets,
    normalize_tickers,
    select_indicators,
    statements_missing,
)
from domain.research.services.screener import ScreenerCriteria, catalog_sectors, screen
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
from infra.providers.batch import fetch_histories, fetch_market_data

logger = logging.getLogger("fincontrol_api.research")

COMPARISON_HISTORY_RANGE = "5y"

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
            total=outcome.matched,
            page=criteria.offset // criteria.limit + 1,
            page_size=criteria.limit,
            candidates=outcome.candidates,
            scanned=outcome.scanned,
            truncated=outcome.truncated,
            arca_classes=sorted(criteria.arca_classes),
            catalog_size=len(catalog),
            catalog_updated_at=max((c.updated_at for c in catalog if c.updated_at), default=None),
        )

    def sectors(self) -> list[str]:
        """Sectors of the B3 catalog, to offer as screener filters."""
        with self.uow_factory() as uow:
            return catalog_sectors(uow.catalog.list_all())

    def treasury(
        self,
        *,
        query: str | None = None,
        indexer: FixedIncomeIndexer | None = None,
        coupon_type: str | None = None,
    ) -> TreasurySearchResponseDTO:
        unavailable_reason: str | None = None
        with self.uow_factory() as uow:
            catalog = uow.treasury_catalog.list_all()
            if not catalog:
                upstream = self.portfolio_service.gateway.list_treasury_bonds()
                if upstream.results:
                    uow.treasury_catalog.upsert(upstream.results)
                    uow.commit()
                    catalog = uow.treasury_catalog.list_all()
                else:
                    unavailable_reason = upstream.unavailable_reason
            treasury_assets = [
                a
                for a in uow.assets.list_all(active_only=True)
                if a.asset_type == AssetType.TREASURY
            ]

        bonds = list(catalog)
        if indexer is not None:
            bonds = [b for b in bonds if b.indexer == indexer]
        if coupon_type:
            bonds = [b for b in bonds if b.coupon_type == coupon_type.strip().lower()]
        if query and query.strip():
            needle = query.strip().casefold()
            bonds = [b for b in bonds if _matches_treasury_query(b, needle)]

        return TreasurySearchResponseDTO(
            results=[
                to_treasury_bond_dto(b, asset_id=_matching_treasury_asset_id(b, treasury_assets))
                for b in bonds
            ],
            total=len(bonds),
            catalog_size=len(catalog),
            catalog_updated_at=max((b.updated_at for b in catalog if b.updated_at), default=None),
            unavailable_reason=unavailable_reason,
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

    def compare(
        self, tickers: list[str], indicators: list[str] | None = None
    ) -> AssetComparisonDTO:
        """Up to five assets side by side, from stored statements and current indicators.

        Companies without stored annual statements get them fetched on demand.
        """
        wanted = normalize_tickers(tickers)
        specs = select_indicators(indicators)
        service = self.portfolio_service
        with self.uow_factory() as uow:
            assets = [_comparison_asset(uow, ticker) for ticker in wanted]
            stored = uow.fundamentals.list_for_many(wanted)
            missing = [
                a for a in assets if statements_missing(a.asset_type, stored.get(a.ticker, []))
            ]
            if self._fetch_statements(uow, missing):
                uow.commit()
                stored = uow.fundamentals.list_for_many(wanted)
            market = fetch_market_data(
                service.gateway,
                assets,
                max_workers=service.fetch_workers,
                timeout_seconds=service.fetch_timeout_seconds,
            )
            prices = fetch_histories(
                service.gateway,
                assets,
                range_period=COMPARISON_HISTORY_RANGE,
                max_workers=service.fetch_workers,
                timeout_seconds=service.fetch_timeout_seconds,
            )
            histories = service.checklist_histories(uow, assets)
            freshness = service.checklist_freshness(uow, assets)
            compared: list[ComparedAsset] = []
            for asset in assets:
                quote = market.quotes.get(asset.ticker)
                fund = market.fundamentals.get(asset.ticker)
                price = (
                    quote.price
                    if quote
                    else (float(asset.manual_price) if asset.manual_price is not None else None)
                )
                statements = stored.get(asset.ticker, [])
                evaluation = service.evaluate_with(
                    asset, fund, histories.get(asset.ticker), freshness.get(asset.ticker)
                )
                valuation = service.value(uow, asset, price, fund)
                compared.append(
                    ComparedAsset(
                        ticker=asset.ticker,
                        name=asset.name,
                        asset_type=asset.asset_type,
                        profile=asset.profile,
                        asset_id=asset.id,
                        currency=quote.currency if quote else asset.currency,
                        price=price,
                        fundamentals=fund,
                        statements=statements,
                        history=historical_metrics(statements) if statements else None,
                        prices=prices.get(asset.ticker, []),
                        valuation_verdict=valuation.verdict.value,
                        fair_value=valuation.fair_value,
                        margin_of_safety=valuation.margin,
                        checklist_score=evaluation.score,
                        checklist_max_score=evaluation.max_score,
                        checklist_normalized_score=evaluation.normalized_score,
                        checklist_coverage_pct=round(evaluation.coverage_pct, 2),
                        checklist_recommendation=evaluation.recommendation.value,
                    )
                )
        return to_asset_comparison_dto(compare_assets(compared, specs))

    def _fetch_statements(self, uow: AbstractUnitOfWork, assets: list[AssetEntity]) -> int:
        """Store the annual statements of `assets` (a provider failure is logged, not raised)."""
        stored = 0
        for asset in assets:
            try:
                snapshots = self.portfolio_service.gateway.get_annual_statements(
                    asset.ticker, asset_type=asset.asset_type
                )
            except Exception:
                logger.exception("Could not fetch the statements of %s", asset.ticker)
                continue
            if snapshots:
                stored += uow.fundamentals.upsert(snapshots)
        return stored

    def _items(self, uow: AbstractUnitOfWork, assets: list[AssetEntity]) -> list[WatchlistItemDTO]:
        service = self.portfolio_service
        market = fetch_market_data(
            service.gateway,
            assets,
            max_workers=service.fetch_workers,
            timeout_seconds=service.fetch_timeout_seconds,
        )
        histories = service.checklist_histories(uow, assets)
        freshness = service.checklist_freshness(uow, assets)
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
            evaluation = service.evaluate_with(
                asset, fund, histories.get(asset.ticker), freshness.get(asset.ticker)
            )
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


def _comparison_asset(uow: AbstractUnitOfWork, ticker: str) -> AssetEntity:
    """The registered asset, or a probe built from the B3 catalog."""
    registered = uow.assets.get_by_ticker(ticker)
    if registered is not None:
        return registered
    listed = uow.catalog.get(ticker)
    if listed is None or listed.asset_type is None:
        raise ValidationError(
            f"{ticker} is neither registered nor in the B3 catalog",
            code="UNKNOWN_INSTRUMENT",
        )
    return AssetEntity(ticker=ticker, name=listed.name, asset_type=listed.asset_type)


def parse_asset_types(values: list[str] | None) -> frozenset[AssetType]:
    return frozenset(AssetType(v) for v in values or [])


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
