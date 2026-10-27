"""Abstract Repository ports (interfaces) operating exclusively on pure Domain Entities.

Services and Handlers depend on these abstractions, never on concrete SQLAlchemy models.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import TYPE_CHECKING

from core.helpers.pagination import PaginatedResult, PaginationParams
from domain.assets.services.history import FundamentalPeriod, FundamentalSnapshot
from domain.shared.entities import (
    AccountEntity,
    AgentApiKeyEntity,
    AssetEntity,
    CatalogInstrument,
    ChecklistAnswer,
    ChecklistEvaluationRecord,
    CorporateEventEntity,
    EarningEntity,
    JobRunEntity,
    MarketSeriesPoint,
    PortfolioSnapshotEntity,
    TransactionEntity,
    WorkerRequestErrorEntity,
)
from domain.shared.enums import SeriesUnit

if TYPE_CHECKING:
    from domain.alerts.services.evaluator import AlertDismissal
    from domain.contributions.services.contribution_plans import SavedContributionPlan
    from domain.policy.services.policy import InvestmentPolicy
    from domain.shared.enums import ContributionPlanStatus


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


class AbstractWorkerErrorRepository(ABC):
    """Repository port for failed external HTTP/API requests recorded during worker jobs."""

    @abstractmethod
    def add(self, error: WorkerRequestErrorEntity) -> WorkerRequestErrorEntity:
        raise NotImplementedError

    @abstractmethod
    def add_many(self, errors: list[WorkerRequestErrorEntity]) -> int:
        raise NotImplementedError

    @abstractmethod
    def list_recent(
        self, *, include_resolved: bool = False, limit: int = 100
    ) -> list[WorkerRequestErrorEntity]:
        """Most recent worker request errors, newest first."""
        raise NotImplementedError

    @abstractmethod
    def count_unresolved(self) -> int:
        """Number of unresolved worker request errors."""
        raise NotImplementedError

    @abstractmethod
    def resolve(self, error_id: int, resolved_at: datetime) -> bool:
        """Mark a single worker request error as resolved."""
        raise NotImplementedError

    @abstractmethod
    def resolve_all(self, resolved_at: datetime) -> int:
        """Mark all unresolved worker request errors as resolved."""
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


class AbstractChecklistRepository(ABC):
    """Repository port for the append-only checklist answers and evaluation history.

    Current answers travel with `AssetEntity.cerrado_answers`; saving an asset appends the
    answers that changed. This port reads the full history and stores evaluations.
    """

    @abstractmethod
    def answer_history(self, asset_id: int) -> list[ChecklistAnswer]:
        """Every recorded answer of an asset, newest first."""
        raise NotImplementedError

    @abstractmethod
    def record_evaluation(self, record: ChecklistEvaluationRecord) -> ChecklistEvaluationRecord:
        raise NotImplementedError

    @abstractmethod
    def latest_evaluation(self, asset_id: int) -> ChecklistEvaluationRecord | None:
        raise NotImplementedError

    @abstractmethod
    def evaluation_history(
        self, asset_id: int, *, limit: int = 104
    ) -> list[ChecklistEvaluationRecord]:
        """Evaluations of an asset, oldest first (at most `limit`, the most recent ones)."""
        raise NotImplementedError


class AbstractCatalogRepository(ABC):
    """Repository port for the daily B3 instrument catalog."""

    @abstractmethod
    def upsert(self, instruments: list[CatalogInstrument]) -> int:
        raise NotImplementedError

    @abstractmethod
    def get(self, ticker: str) -> CatalogInstrument | None:
        raise NotImplementedError

    @abstractmethod
    def list_all(self) -> list[CatalogInstrument]:
        """Whole catalog, highest financial volume first."""
        raise NotImplementedError


class AbstractContributionPlanRepository(ABC):
    """Repository port for persisted contribution plans."""

    @abstractmethod
    def add(self, saved: SavedContributionPlan) -> SavedContributionPlan:
        raise NotImplementedError

    @abstractmethod
    def update(self, saved: SavedContributionPlan) -> SavedContributionPlan:
        raise NotImplementedError

    @abstractmethod
    def get(self, plan_id: int) -> SavedContributionPlan | None:
        raise NotImplementedError

    @abstractmethod
    def list_recent(
        self, *, status: ContributionPlanStatus | None = None, limit: int = 20
    ) -> list[SavedContributionPlan]:
        """Newest first."""
        raise NotImplementedError


class AbstractCorporateEventRepository(ABC):
    """Repository port for splits, reverse splits and bonus issues."""

    @abstractmethod
    def add(self, event: CorporateEventEntity) -> CorporateEventEntity:
        raise NotImplementedError

    @abstractmethod
    def get(self, event_id: int) -> CorporateEventEntity | None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, event_id: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list_all(self, *, asset_id: int | None = None) -> list[CorporateEventEntity]:
        """Events ordered by ex-date."""
        raise NotImplementedError


class AbstractLedgerImportRepository(ABC):
    """Deduplication of imported ledger lines (trades, earnings, events) by content hash."""

    @abstractmethod
    def existing_hashes(self, hashes: list[str]) -> set[str]:
        raise NotImplementedError


class AbstractAlertDismissalRepository(ABC):
    """Alerts the user chose to hide (for a while or until the condition clears)."""

    @abstractmethod
    def list_all(self) -> list[AlertDismissal]:
        raise NotImplementedError

    @abstractmethod
    def upsert(self, dismissal: AlertDismissal) -> AlertDismissal:
        raise NotImplementedError

    @abstractmethod
    def delete(self, key: str) -> bool:
        raise NotImplementedError


class AbstractAgentKeyRepository(ABC):
    """Repository port for MCP agent API keys."""

    @abstractmethod
    def add(self, key: AgentApiKeyEntity) -> AgentApiKeyEntity:
        raise NotImplementedError

    @abstractmethod
    def update(self, key: AgentApiKeyEntity) -> AgentApiKeyEntity:
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, key_id: int) -> AgentApiKeyEntity | None:
        raise NotImplementedError

    @abstractmethod
    def get_by_hash(self, key_hash: str) -> AgentApiKeyEntity | None:
        raise NotImplementedError

    @abstractmethod
    def list_active(self, *, user_id: str | None = None) -> list[AgentApiKeyEntity]:
        """Non-revoked keys, ordered newest first."""
        raise NotImplementedError

    @abstractmethod
    def touch_last_used(self, key_id: int, used_at: datetime) -> None:
        raise NotImplementedError
