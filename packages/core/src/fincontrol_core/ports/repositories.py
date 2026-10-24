"""Abstract Repository ports (interfaces) operating exclusively on pure Domain Entities.

Services and Handlers depend on these abstractions, never on concrete SQLAlchemy models.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal

from fincontrol_core.domain.entities import (
    ArcaTargetEntity,
    AssetEntity,
    EarningEntity,
    MarketSeriesPoint,
    PortfolioSnapshotEntity,
    TransactionEntity,
)
from fincontrol_core.domain.enums import ArcaClass, IntraClassStrategy
from fincontrol_core.domain.pagination import PaginatedResult, PaginationParams


class AbstractAssetRepository(ABC):
    """Repository port for Asset aggregates (including optional FixedIncomeTermEntity)."""

    @abstractmethod
    def add(self, asset: AssetEntity) -> AssetEntity:
        raise NotImplementedError

    @abstractmethod
    def update(self, asset: AssetEntity) -> AssetEntity:
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, asset_id: int) -> AssetEntity | None:
        raise NotImplementedError

    @abstractmethod
    def get_by_ticker(self, ticker: str) -> AssetEntity | None:
        raise NotImplementedError

    @abstractmethod
    def list_all(self, *, active_only: bool = True) -> list[AssetEntity]:
        raise NotImplementedError

    @abstractmethod
    def list_paginated(
        self,
        params: PaginationParams,
        *,
        arca_class: str | None = None,
        asset_type: str | None = None,
        use_cerrado: bool | None = None,
        active_only: bool = True,
    ) -> PaginatedResult[AssetEntity]:
        raise NotImplementedError

    @abstractmethod
    def delete(self, asset_id: int, *, hard: bool = False) -> bool:
        raise NotImplementedError


class AbstractTransactionRepository(ABC):
    """Repository port for buy/sell trade transactions."""

    @abstractmethod
    def add(self, transaction: TransactionEntity) -> TransactionEntity:
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, transaction_id: int) -> TransactionEntity | None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, transaction_id: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list_for_asset(self, asset_id: int) -> list[TransactionEntity]:
        raise NotImplementedError

    @abstractmethod
    def list_paginated(
        self,
        params: PaginationParams,
        *,
        asset_id: int | None = None,
        kind: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> PaginatedResult[TransactionEntity]:
        raise NotImplementedError


class AbstractEarningRepository(ABC):
    """Repository port for received earnings (dividends, JCP, FII yields, coupons)."""

    @abstractmethod
    def add(self, earning: EarningEntity) -> EarningEntity:
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, earning_id: int) -> EarningEntity | None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, earning_id: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list_for_asset(self, asset_id: int) -> list[EarningEntity]:
        raise NotImplementedError

    @abstractmethod
    def list_paginated(
        self,
        params: PaginationParams,
        *,
        asset_id: int | None = None,
        kind: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> PaginatedResult[EarningEntity]:
        raise NotImplementedError


class AbstractArcaTargetRepository(ABC):
    """Repository port for ARCA macro-allocation targets."""

    @abstractmethod
    def get_all(self) -> list[ArcaTargetEntity]:
        raise NotImplementedError

    @abstractmethod
    def seed_defaults(self) -> list[ArcaTargetEntity]:
        raise NotImplementedError

    @abstractmethod
    def upsert_targets(
        self,
        targets: dict[ArcaClass, Decimal],
        strategies: dict[ArcaClass, IntraClassStrategy] | None = None,
    ) -> list[ArcaTargetEntity]:
        raise NotImplementedError


class AbstractMarketSeriesRepository(ABC):
    """Repository port for historical prices and macroeconomic benchmark series."""

    @abstractmethod
    def upsert_points(self, symbol: str, points: list[tuple[date, float]]) -> int:
        raise NotImplementedError

    @abstractmethod
    def list_series(
        self,
        symbol: str,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[MarketSeriesPoint]:
        raise NotImplementedError


class AbstractPortfolioSnapshotRepository(ABC):
    """Repository port for daily consolidated portfolio snapshots."""

    @abstractmethod
    def upsert(self, snapshot: PortfolioSnapshotEntity) -> PortfolioSnapshotEntity:
        raise NotImplementedError

    @abstractmethod
    def list_range(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[PortfolioSnapshotEntity]:
        raise NotImplementedError
