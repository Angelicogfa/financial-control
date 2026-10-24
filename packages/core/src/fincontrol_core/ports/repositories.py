"""Abstract Repository ports (interfaces) operating exclusively on pure Domain Entities.

Services and Handlers depend on these abstractions, never on concrete SQLAlchemy models.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from fincontrol_core.domain.entities import (
    AccountEntity,
    AssetEntity,
    EarningEntity,
    JobRunEntity,
    MarketSeriesPoint,
    PortfolioSnapshotEntity,
    TransactionEntity,
)
from fincontrol_core.domain.enums import SeriesUnit
from fincontrol_core.domain.pagination import PaginatedResult, PaginationParams
from fincontrol_core.fundamentals.history import FundamentalPeriod, FundamentalSnapshot
from fincontrol_core.policy.models import InvestmentPolicy


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
    def update(self, transaction: TransactionEntity) -> TransactionEntity:
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
        account_id: int | None = None,
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
    def update(self, earning: EarningEntity) -> EarningEntity:
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
        account_id: int | None = None,
    ) -> PaginatedResult[EarningEntity]:
        raise NotImplementedError


class AbstractPolicyRepository(ABC):
    """Repository port for versioned investment policies (append-only)."""

    @abstractmethod
    def get_current(self) -> InvestmentPolicy | None:
        raise NotImplementedError

    @abstractmethod
    def add(self, policy: InvestmentPolicy) -> InvestmentPolicy:
        """Store `policy` as the next version and return it with version and timestamp."""
        raise NotImplementedError

    @abstractmethod
    def list_versions(self, limit: int = 20) -> list[InvestmentPolicy]:
        """Most recent versions first."""
        raise NotImplementedError


class AbstractMarketSeriesRepository(ABC):
    """Repository port for historical prices and macroeconomic benchmark series."""

    @abstractmethod
    def upsert_points(
        self, symbol: str, points: list[tuple[date, float]], *, unit: SeriesUnit
    ) -> int:
        raise NotImplementedError

    @abstractmethod
    def date_range(self, symbol: str) -> tuple[date, date] | None:
        """Return (first, last) stored reference dates for a symbol, or None if empty."""
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

    @abstractmethod
    def latest_before(self, snapshot_date: date) -> PortfolioSnapshotEntity | None:
        """Most recent snapshot strictly before `snapshot_date`."""
        raise NotImplementedError

    @abstractmethod
    def delete_range(self, *, date_from: date | None = None, date_to: date | None = None) -> int:
        raise NotImplementedError


class AbstractJobRunRepository(ABC):
    """Repository port for background job executions."""

    @abstractmethod
    def add(self, run: JobRunEntity) -> JobRunEntity:
        raise NotImplementedError

    @abstractmethod
    def update(self, run: JobRunEntity) -> JobRunEntity:
        raise NotImplementedError

    @abstractmethod
    def latest_per_job(self) -> list[JobRunEntity]:
        """Most recent execution of each job name."""
        raise NotImplementedError


class AbstractAccountRepository(ABC):
    """Repository port for custody accounts."""

    @abstractmethod
    def add(self, account: AccountEntity) -> AccountEntity:
        raise NotImplementedError

    @abstractmethod
    def update(self, account: AccountEntity) -> AccountEntity:
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, account_id: int) -> AccountEntity | None:
        raise NotImplementedError

    @abstractmethod
    def list_all(self, *, active_only: bool = False) -> list[AccountEntity]:
        raise NotImplementedError

    @abstractmethod
    def get_default(self) -> AccountEntity | None:
        """Oldest active account, used when a trade does not name one."""
        raise NotImplementedError


class AbstractFundamentalsRepository(ABC):
    """Repository port for yearly statement snapshots, keyed by ticker."""

    @abstractmethod
    def upsert(self, snapshots: list[FundamentalSnapshot]) -> int:
        """Insert or replace snapshots by (ticker, reference_date, period)."""
        raise NotImplementedError

    @abstractmethod
    def list_for(
        self, ticker: str, *, period: FundamentalPeriod = FundamentalPeriod.ANNUAL
    ) -> list[FundamentalSnapshot]:
        """Snapshots of a ticker, oldest first."""
        raise NotImplementedError

    @abstractmethod
    def list_for_many(
        self, tickers: list[str], *, period: FundamentalPeriod = FundamentalPeriod.ANNUAL
    ) -> dict[str, list[FundamentalSnapshot]]:
        raise NotImplementedError
