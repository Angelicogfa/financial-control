"""SQLAlchemy repositories: daily portfolio snapshots and saved contribution plans.

They take and return pure domain entities and never commit
(the transaction boundary belongs to `SqlAlchemyUnitOfWork`)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from core.errors import NotFoundError
from domain.contributions.services.contribution_plans import SavedContributionPlan, plan_to_payload
from domain.shared.entities import (
    PortfolioSnapshotEntity,
)
from domain.shared.enums import ContributionPlanStatus
from domain.shared.repositories import (
    AbstractContributionPlanRepository,
    AbstractPortfolioSnapshotRepository,
)
from infra.data.mappers.portfolio import (
    to_portfolio_snapshot_entity,
    to_saved_contribution_plan,
)
from infra.data.models.portfolio import ContributionPlanModel, PortfolioSnapshotModel


def _money(value: float) -> Decimal:
    return Decimal(str(round(value, 2)))


class SqlAlchemyPortfolioSnapshotRepository(AbstractPortfolioSnapshotRepository):
    """SQLAlchemy implementation of AbstractPortfolioSnapshotRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, snapshot: PortfolioSnapshotEntity) -> PortfolioSnapshotEntity:
        model = PortfolioSnapshotModel(
            snapshot_date=snapshot.snapshot_date,
            invested_value=_money(snapshot.invested_value),
            market_value=_money(snapshot.market_value),
            unrealized_pnl=_money(snapshot.unrealized_pnl),
            realized_pnl_cum=_money(snapshot.realized_pnl_cum),
            earnings_cum=_money(snapshot.earnings_cum),
            consolidated_pnl=_money(snapshot.consolidated_pnl),
            net_flow=_money(snapshot.net_flow),
            by_class=snapshot.by_class,
        )
        merged = self.session.merge(model)
        self.session.flush()
        return to_portfolio_snapshot_entity(merged)

    def list_range(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[PortfolioSnapshotEntity]:
        stmt = select(PortfolioSnapshotModel)
        if date_from is not None:
            stmt = stmt.where(PortfolioSnapshotModel.snapshot_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(PortfolioSnapshotModel.snapshot_date <= date_to)
        stmt = stmt.order_by(PortfolioSnapshotModel.snapshot_date.asc())
        return [to_portfolio_snapshot_entity(m) for m in self.session.scalars(stmt).all()]

    def latest_before(self, snapshot_date: date) -> PortfolioSnapshotEntity | None:
        stmt = (
            select(PortfolioSnapshotModel)
            .where(PortfolioSnapshotModel.snapshot_date < snapshot_date)
            .order_by(PortfolioSnapshotModel.snapshot_date.desc())
            .limit(1)
        )
        model = self.session.scalar(stmt)
        return to_portfolio_snapshot_entity(model) if model else None

    def delete_range(self, *, date_from: date | None = None, date_to: date | None = None) -> int:
        stmt = delete(PortfolioSnapshotModel)
        if date_from is not None:
            stmt = stmt.where(PortfolioSnapshotModel.snapshot_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(PortfolioSnapshotModel.snapshot_date <= date_to)
        result = self.session.execute(stmt)
        self.session.flush()
        return int(result.rowcount or 0)


class SqlAlchemyContributionPlanRepository(AbstractContributionPlanRepository):
    """SQLAlchemy implementation of AbstractContributionPlanRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _apply(model: ContributionPlanModel, saved: SavedContributionPlan) -> None:
        model.status = saved.status.value
        model.amount_brl = Decimal(str(saved.plan.contribution_amount_brl))
        model.strategy_override = saved.strategy_override.value if saved.strategy_override else None
        model.policy_version = saved.policy_version
        model.account_id = saved.account_id
        model.payload = plan_to_payload(saved.plan)
        model.transaction_ids = list(saved.transaction_ids)
        model.confirmed_at = saved.confirmed_at
        model.discarded_at = saved.discarded_at

    def add(self, saved: SavedContributionPlan) -> SavedContributionPlan:
        model = ContributionPlanModel(created_at=saved.created_at or datetime.now(UTC))
        self._apply(model, saved)
        self.session.add(model)
        self.session.flush()
        return to_saved_contribution_plan(model)

    def update(self, saved: SavedContributionPlan) -> SavedContributionPlan:
        model = self.session.get(ContributionPlanModel, saved.id) if saved.id else None
        if model is None:
            raise NotFoundError(f"Contribution plan id={saved.id} not found")
        self._apply(model, saved)
        self.session.flush()
        return to_saved_contribution_plan(model)

    def get(self, plan_id: int) -> SavedContributionPlan | None:
        model = self.session.get(ContributionPlanModel, plan_id)
        return to_saved_contribution_plan(model) if model else None

    def list_recent(
        self, *, status: ContributionPlanStatus | None = None, limit: int = 20
    ) -> list[SavedContributionPlan]:
        stmt = select(ContributionPlanModel).order_by(ContributionPlanModel.id.desc()).limit(limit)
        if status is not None:
            stmt = stmt.where(ContributionPlanModel.status == status.value)
        return [to_saved_contribution_plan(m) for m in self.session.scalars(stmt).all()]
