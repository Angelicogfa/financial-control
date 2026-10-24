"""Persistence layer for Financial Control (SQLAlchemy 2.0, Alembic, Repositories, UnitOfWork)."""

from fincontrol_persistence.db import Base, build_engine, build_session_factory
from fincontrol_persistence.models import (
    AssetModel,
    EarningModel,
    FixedIncomeTermModel,
    InvestmentPolicyModel,
    MarketSeriesModel,
    PortfolioSnapshotModel,
    TransactionModel,
)
from fincontrol_persistence.repositories import (
    AssetRepository,
    EarningRepository,
    MarketSeriesRepository,
    PolicyRepository,
    PortfolioSnapshotRepository,
    SqlAlchemyAssetRepository,
    SqlAlchemyEarningRepository,
    SqlAlchemyMarketSeriesRepository,
    SqlAlchemyPolicyRepository,
    SqlAlchemyPortfolioSnapshotRepository,
    SqlAlchemyTransactionRepository,
    TransactionRepository,
)
from fincontrol_persistence.unit_of_work import SqlAlchemyUnitOfWork

__all__ = [
    "InvestmentPolicyModel",
    "PolicyRepository",
    "AssetModel",
    "AssetRepository",
    "Base",
    "EarningModel",
    "EarningRepository",
    "FixedIncomeTermModel",
    "MarketSeriesModel",
    "MarketSeriesRepository",
    "PortfolioSnapshotModel",
    "PortfolioSnapshotRepository",
    "SqlAlchemyPolicyRepository",
    "SqlAlchemyAssetRepository",
    "SqlAlchemyEarningRepository",
    "SqlAlchemyMarketSeriesRepository",
    "SqlAlchemyPortfolioSnapshotRepository",
    "SqlAlchemyTransactionRepository",
    "SqlAlchemyUnitOfWork",
    "TransactionModel",
    "TransactionRepository",
    "build_engine",
    "build_session_factory",
]
