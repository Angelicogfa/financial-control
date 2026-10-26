"""ORM model <-> domain entity mappers: daily portfolio snapshots and saved contribution plans."""

from __future__ import annotations

from fincontrol_core.domain.entities import (
    PortfolioSnapshotEntity,
)
from fincontrol_core.domain.enums import (
    ContributionPlanStatus,
    IntraClassStrategy,
)
from fincontrol_core.portfolio.contribution_plans import SavedContributionPlan, plan_from_payload

from fincontrol_persistence.models.portfolio import ContributionPlanModel, PortfolioSnapshotModel


def to_portfolio_snapshot_entity(model: PortfolioSnapshotModel) -> PortfolioSnapshotEntity:
    return PortfolioSnapshotEntity(
        snapshot_date=model.snapshot_date,
        invested_value=float(model.invested_value),
        market_value=float(model.market_value),
        unrealized_pnl=float(model.unrealized_pnl),
        realized_pnl_cum=float(model.realized_pnl_cum),
        earnings_cum=float(model.earnings_cum),
        consolidated_pnl=float(model.consolidated_pnl),
        net_flow=float(model.net_flow),
        by_class=dict(model.by_class or {}),
    )


def to_saved_contribution_plan(model: ContributionPlanModel) -> SavedContributionPlan:
    return SavedContributionPlan(
        id=model.id,
        plan=plan_from_payload(model.payload),
        status=ContributionPlanStatus(model.status),
        strategy_override=(
            IntraClassStrategy(model.strategy_override) if model.strategy_override else None
        ),
        policy_version=model.policy_version,
        account_id=model.account_id,
        transaction_ids=tuple(model.transaction_ids or ()),
        created_at=model.created_at,
        confirmed_at=model.confirmed_at,
        discarded_at=model.discarded_at,
    )
