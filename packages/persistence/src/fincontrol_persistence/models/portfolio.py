"""SQLAlchemy 2.0 ORM models: daily portfolio snapshots and saved contribution plans.

Table and column names are in English."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from fincontrol_persistence.core.db import Base
from fincontrol_persistence.models.common import utc_now


class PortfolioSnapshotModel(Base):
    """Daily consolidated portfolio snapshot for historical evolution and TWR calculation."""

    __tablename__ = "portfolio_snapshots"

    snapshot_date: Mapped[date] = mapped_column(Date, primary_key=True)
    invested_value: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    market_value: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    realized_pnl_cum: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    earnings_cum: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    consolidated_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    net_flow: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    by_class: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class ContributionPlanModel(Base):
    """Contribution plan as suggested (payload) and what happened to it (status)."""

    __tablename__ = "contribution_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    amount_brl: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    strategy_override: Mapped[str | None] = mapped_column(String(24), nullable=True)
    policy_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    account_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("accounts.id"), nullable=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    transaction_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    discarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
