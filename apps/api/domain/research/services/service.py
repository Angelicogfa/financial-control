"""Application service for the research module.

Scope: registering a researched asset (the single path used by the watchlist and by the B3
import) and fetching its yearly statements right after it is registered.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from controllers.shared.dependencies import UoWFactory
from core.errors import ValidationError
from domain.assets.services.etf_exposure import suggest_arca_class
from domain.assets.services.history import STATEMENT_TYPES
from domain.shared.entities import AssetEntity
from domain.shared.enums import ArcaClass, AssetType
from domain.shared.unit_of_work import AbstractUnitOfWork
from infra.providers.gateway import CachedMarketGateway

logger = logging.getLogger("fincontrol_api.research")


def suggested_arca_class(ticker: str, asset_type: AssetType) -> ArcaClass:
    """The ARCA quadrant proposed for a new asset (the user may pick another one)."""
    return suggest_arca_class(ticker, asset_type).arca_class


def register_researched_asset(
    uow: AbstractUnitOfWork,
    ticker: str,
    *,
    asset_type: AssetType | None = None,
    name: str | None = None,
    arca_class: ArcaClass | None = None,
) -> AssetEntity:
    """Register a new asset the way the research flow does: B3 catalog first, then the
    informed type and name, and the chosen ARCA quadrant (or the suggested one).

    Does not commit: the caller's Unit of Work owns the transaction.
    """
    ticker = ticker.strip().upper()
    listed = uow.catalog.get(ticker)
    asset_type = asset_type or (listed.asset_type if listed else None)
    if asset_type is None:
        raise ValidationError(
            f"{ticker} is not in the catalog; inform asset_type", code="UNKNOWN_INSTRUMENT"
        )
    return uow.assets.add(
        AssetEntity(
            ticker=ticker,
            name=name or (listed.name if listed else ticker),
            asset_type=asset_type,
            arca_class=arca_class or suggested_arca_class(ticker, asset_type),
        )
    )


class StatementRefresher:
    """Fetch and store the yearly statements of newly researched companies.

    Runs after the HTTP response (FastAPI background task): a provider failure is logged and
    left to the worker's weekly `refresh_fundamentals` job, never surfaced to the request.
    """

    def __init__(self, uow_factory: UoWFactory, gateway: CachedMarketGateway) -> None:
        self.uow_factory = uow_factory
        self.gateway = gateway

    def refresh(self, tickers: Iterable[str]) -> dict[str, int]:
        wanted = {t.strip().upper() for t in tickers if t.strip()}
        if not wanted:
            return {}
        with self.uow_factory() as uow:
            targets = {
                a.ticker: a.asset_type
                for a in uow.assets.list_all(active_only=True)
                if a.ticker in wanted and a.asset_type in STATEMENT_TYPES
            }
        stored: dict[str, int] = {}
        for ticker, asset_type in sorted(targets.items()):
            try:
                snapshots = self.gateway.get_annual_statements(
                    ticker, asset_type=asset_type, bypass_cache=True
                )
                if not snapshots:
                    stored[ticker] = 0
                    continue
                with self.uow_factory() as uow:
                    stored[ticker] = uow.fundamentals.upsert(snapshots)
                    uow.commit()
            except Exception:
                logger.exception("Could not fetch the statements of %s", ticker)
                stored[ticker] = 0
        return stored
