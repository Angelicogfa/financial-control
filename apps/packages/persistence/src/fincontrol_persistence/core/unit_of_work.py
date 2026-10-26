"""SQLAlchemy implementation of AbstractUnitOfWork."""

from __future__ import annotations

from types import TracebackType

from fincontrol_core.ports.unit_of_work import AbstractUnitOfWork
from sqlalchemy.orm import Session, sessionmaker

from fincontrol_persistence.core.db import get_default_session_factory
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


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    """Concrete Unit of Work managing a SQLAlchemy Session and all domain repositories."""

    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        self._session_factory = session_factory or get_default_session_factory()
        self.session: Session | None = None

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        self.session = self._session_factory()
        self.assets = SqlAlchemyAssetRepository(self.session)
        self.transactions = SqlAlchemyTransactionRepository(self.session)
        self.earnings = SqlAlchemyEarningRepository(self.session)
        self.policies = SqlAlchemyPolicyRepository(self.session)
        self.accounts = SqlAlchemyAccountRepository(self.session)
        self.market_series = SqlAlchemyMarketSeriesRepository(self.session)
        self.snapshots = SqlAlchemyPortfolioSnapshotRepository(self.session)
        self.job_runs = SqlAlchemyJobRunRepository(self.session)
        self.fundamentals = SqlAlchemyFundamentalsRepository(self.session)
        self.checklists = SqlAlchemyChecklistRepository(self.session)
        self.catalog = SqlAlchemyCatalogRepository(self.session)
        self.contribution_plans = SqlAlchemyContributionPlanRepository(self.session)
        self.corporate_events = SqlAlchemyCorporateEventRepository(self.session)
        self.ledger_imports = SqlAlchemyLedgerImportRepository(self.session)
        self.alert_dismissals = SqlAlchemyAlertDismissalRepository(self.session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        try:
            super().__exit__(exc_type, exc_val, exc_tb)
        finally:
            if self.session is not None:
                self.session.close()
                self.session = None

    def commit(self) -> None:
        if self.session is None:
            raise RuntimeError("Cannot commit outside an active UnitOfWork context")
        self.session.commit()

    def rollback(self) -> None:
        if self.session is not None:
            self.session.rollback()
