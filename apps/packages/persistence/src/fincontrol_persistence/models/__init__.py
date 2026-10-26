"""ORM models, one module per feature.

Importing this package registers every model on `Base.metadata` (Alembic and the
relationship() string targets rely on it).
"""

from __future__ import annotations

from fincontrol_persistence.models.accounts import AccountModel
from fincontrol_persistence.models.alerts import AlertDismissalModel
from fincontrol_persistence.models.assets import (
    AssetModel,
    ChecklistAnswerModel,
    ChecklistEvaluationModel,
    FixedIncomeTermModel,
)
from fincontrol_persistence.models.jobs import JobRunModel
from fincontrol_persistence.models.ledger import CorporateEventModel, EarningModel, TransactionModel
from fincontrol_persistence.models.market import (
    FundamentalSnapshotModel,
    InstrumentCatalogModel,
    MarketSeriesModel,
)
from fincontrol_persistence.models.policy import InvestmentPolicyModel
from fincontrol_persistence.models.portfolio import ContributionPlanModel, PortfolioSnapshotModel

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
