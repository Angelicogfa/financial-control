"""ORM models, one module per feature.

Importing this package registers every model on `Base.metadata` (Alembic and the
relationship() string targets rely on it).
"""

from __future__ import annotations

from infra.data.models.accounts import AccountModel
from infra.data.models.alerts import AlertDismissalModel
from infra.data.models.assets import (
    AssetModel,
    ChecklistAnswerModel,
    ChecklistEvaluationModel,
    FixedIncomeTermModel,
)
from infra.data.models.jobs import JobRunModel
from infra.data.models.ledger import CorporateEventModel, EarningModel, TransactionModel
from infra.data.models.market import (
    FundamentalSnapshotModel,
    InstrumentCatalogModel,
    MarketSeriesModel,
)
from infra.data.models.policy import InvestmentPolicyModel
from infra.data.models.portfolio import ContributionPlanModel, PortfolioSnapshotModel

__all__ = [
    "AccountModel",
    "AlertDismissalModel",
    "AssetModel",
    "ChecklistAnswerModel",
    "ChecklistEvaluationModel",
    "ContributionPlanModel",
    "CorporateEventModel",
    "EarningModel",
    "FixedIncomeTermModel",
    "FundamentalSnapshotModel",
    "InstrumentCatalogModel",
    "InvestmentPolicyModel",
    "JobRunModel",
    "MarketSeriesModel",
    "PortfolioSnapshotModel",
    "TransactionModel",
]
