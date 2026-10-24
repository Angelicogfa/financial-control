"""Persistence layer for Financial Control (SQLAlchemy 2.0, Alembic, Repositories, UnitOfWork)."""

from fincontrol_persistence.db import Base, build_engine, build_session_factory
from fincontrol_persistence.models import (
    ArcaTargetModel,
    AssetModel,
    EarningModel,
    FixedIncomeTermModel,
    MarketSeriesModel,
    PortfolioSnapshotModel,
    TransactionModel,
)
from fincontrol_persistence.repositories import (
    ArcaTargetRepository,
    AssetRepository,
    EarningRepository,
    MarketSeriesRepository,
    PortfolioSnapshotRepository,
    SqlAlchemyArcaTargetRepository,
    SqlAlchemyAssetRepository,
    SqlAlchemyEarningRepository,
    SqlAlchemyMarketSeriesRepository,
    SqlAlchemyPortfolioSnapshotRepository,
    SqlAlchemyTransactionRepository,
    TransactionRepository,
)
from fincontrol_persistence.unit_of_work import SqlAlchemyUnitOfWork

__all__ = [
    "ArcaTargetModel",
    "ArcaTargetRepository",
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
    "SqlAlchemyArcaTargetRepository",
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
