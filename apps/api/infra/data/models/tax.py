"""SQLAlchemy 2.0 ORM models of the tax rule registry and of the monthly assessments."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from infra.data.db import Base


class TaxRuleModel(Base):
    """IR/IOF rates of a tax regime in force between `valid_from` and `valid_to`."""

    __tablename__ = "tax_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    regime: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    tax_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # [{"up_to_days": int | None, "rate": float}, ...] ordered by day limit (ADR 0006 fractions)
    brackets: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    legal_basis: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    description: Mapped[str] = mapped_column(String(400), nullable=False, default="")


class MonthlyTaxAssessmentModel(Base):
    """A month and category of the income tax assessment (Phase 48.R7); `TOTAL` has the DARF."""

    __tablename__ = "monthly_tax_assessments"
    __table_args__ = (
        UniqueConstraint("month", "category", name="uq_monthly_tax_assessments_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    month: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    sales_brl: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    result_brl: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    loss_out_brl: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    taxable_brl: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    tax_brl: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    darf_brl: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paid_on: Mapped[date | None] = mapped_column(Date, nullable=True)
