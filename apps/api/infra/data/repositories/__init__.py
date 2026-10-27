"""SQLAlchemy repositories, one module per feature."""

from __future__ import annotations

from infra.data.repositories.accounts import SqlAlchemyAccountRepository
from infra.data.repositories.agent_keys import SqlAlchemyAgentKeyRepository
from infra.data.repositories.alerts import SqlAlchemyAlertDismissalRepository
from infra.data.repositories.assets import (
    SqlAlchemyAssetRepository,
    SqlAlchemyChecklistRepository,
)
from infra.data.repositories.jobs import SqlAlchemyJobRunRepository
from infra.data.repositories.ledger import (
    SqlAlchemyCorporateEventRepository,
    SqlAlchemyEarningRepository,
    SqlAlchemyLedgerImportRepository,
    SqlAlchemyTransactionRepository,
)
from infra.data.repositories.market import (
    SqlAlchemyCatalogRepository,
    SqlAlchemyFundamentalsRepository,
    SqlAlchemyMarketSeriesRepository,
)
from infra.data.repositories.policy import SqlAlchemyPolicyRepository
from infra.data.repositories.portfolio import (
    SqlAlchemyContributionPlanRepository,
    SqlAlchemyPortfolioSnapshotRepository,
)

__all__ = [
    "SqlAlchemyAccountRepository",
    "SqlAlchemyAgentKeyRepository",
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
