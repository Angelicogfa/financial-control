"""SQLAlchemy repositories, one module per feature."""

from __future__ import annotations

from fincontrol_persistence.repositories.accounts import SqlAlchemyAccountRepository
from fincontrol_persistence.repositories.alerts import SqlAlchemyAlertDismissalRepository
from fincontrol_persistence.repositories.assets import (
    SqlAlchemyAssetRepository,
    SqlAlchemyChecklistRepository,
)
from fincontrol_persistence.repositories.jobs import SqlAlchemyJobRunRepository
from fincontrol_persistence.repositories.ledger import (
    SqlAlchemyCorporateEventRepository,
    SqlAlchemyEarningRepository,
    SqlAlchemyLedgerImportRepository,
    SqlAlchemyTransactionRepository,
)
from fincontrol_persistence.repositories.market import (
    SqlAlchemyCatalogRepository,
    SqlAlchemyFundamentalsRepository,
    SqlAlchemyMarketSeriesRepository,
)
from fincontrol_persistence.repositories.policy import SqlAlchemyPolicyRepository
from fincontrol_persistence.repositories.portfolio import (
    SqlAlchemyContributionPlanRepository,
    SqlAlchemyPortfolioSnapshotRepository,
)

__all__ = [
    "SqlAlchemyAccountRepository",
    "SqlAlchemyAlertDismissalRepository",
    "SqlAlchemyAssetRepository",
    "SqlAlchemyCatalogRepository",
    "SqlAlchemyChecklistRepository",
    "SqlAlchemyContributionPlanRepository",
    "SqlAlchemyCorporateEventRepository",
    "SqlAlchemyEarningRepository",
    "SqlAlchemyFundamentalsRepository",
    "SqlAlchemyJobRunRepository",
    "SqlAlchemyLedgerImportRepository",
    "SqlAlchemyMarketSeriesRepository",
    "SqlAlchemyPolicyRepository",
    "SqlAlchemyPortfolioSnapshotRepository",
    "SqlAlchemyTransactionRepository",
]
