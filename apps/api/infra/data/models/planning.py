"""SQLAlchemy 2.0 ORM model of the goals of Planejar (Phase 48.R8)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from infra.data.db import Base


class GoalModel(Base):
    """A wealth or a monthly passive income to reach by a date."""

    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    target_brl: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    monthly_contribution_brl: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    annual_return: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    income_yield: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
