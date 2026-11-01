"""SQLAlchemy 2.0 ORM model of the live scoreboard (Phase 45.8a)."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import JSON, Date, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from infra.data.db import Base


class ComparisonPortfolioModel(Base):
    """One comparison portfolio with its book and its record of values."""

    __tablename__ = "comparison_portfolios"
    __table_args__ = (UniqueConstraint("key", "variant", name="uq_comparison_portfolios_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(32), nullable=False)
    variant: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    created_on: Mapped[date] = mapped_column(Date, nullable=False)
    state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    points: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
