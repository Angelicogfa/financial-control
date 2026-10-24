"""Unit of Work port (interface) for managing atomic transactions across repositories."""

from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType

from fincontrol_core.ports.repositories import (
    AbstractAccountRepository,
    AbstractAssetRepository,
    AbstractEarningRepository,
    AbstractFundamentalsRepository,
    AbstractJobRunRepository,
    AbstractMarketSeriesRepository,
    AbstractPolicyRepository,
    AbstractPortfolioSnapshotRepository,
    AbstractTransactionRepository,
)


class AbstractUnitOfWork(ABC):
    """Defines an atomic persistence boundary exposing all domain repositories."""

    assets: AbstractAssetRepository
    transactions: AbstractTransactionRepository
    earnings: AbstractEarningRepository
    policies: AbstractPolicyRepository
    accounts: AbstractAccountRepository
    market_series: AbstractMarketSeriesRepository
    snapshots: AbstractPortfolioSnapshotRepository
    job_runs: AbstractJobRunRepository
    fundamentals: AbstractFundamentalsRepository

    def __enter__(self) -> AbstractUnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self.rollback()

    @abstractmethod
    def commit(self) -> None:
        """Commit the current unit of work transaction."""
        raise NotImplementedError

    @abstractmethod
    def rollback(self) -> None:
        """Roll back any uncommitted changes in the current transaction."""
        raise NotImplementedError
