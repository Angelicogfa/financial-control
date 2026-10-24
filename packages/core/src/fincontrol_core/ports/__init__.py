"""Application and domain ports (Repository interfaces and Unit of Work contract)."""

from fincontrol_core.ports.repositories import (
    AbstractAssetRepository,
    AbstractEarningRepository,
    AbstractMarketSeriesRepository,
    AbstractPolicyRepository,
    AbstractPortfolioSnapshotRepository,
    AbstractTransactionRepository,
)
from fincontrol_core.ports.unit_of_work import AbstractUnitOfWork

__all__ = [
    "AbstractPolicyRepository",
    "AbstractAssetRepository",
    "AbstractEarningRepository",
    "AbstractMarketSeriesRepository",
    "AbstractPortfolioSnapshotRepository",
    "AbstractTransactionRepository",
    "AbstractUnitOfWork",
]
