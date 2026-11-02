"""SQLAlchemy 2.0 ORM models of the position check against the B3 statement (Phase 48.R5)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infra.data.db import Base


class PositionReconciliationModel(Base):
    """One check: the Posição statement of a reference date against the ledger."""

    __tablename__ = "position_reconciliations"
    __table_args__ = (
        UniqueConstraint("reference_date", "file_hash", name="uq_position_reconciliations_file"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reference_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    lines: Mapped[list[PositionReconciliationLineModel]] = relationship(
        back_populates="reconciliation",
        cascade="all, delete-orphan",
        order_by="PositionReconciliationLineModel.id",
    )


class PositionReconciliationLineModel(Base):
    """One ticker and account of a check, with both quantities and its resolution."""

    __tablename__ = "position_reconciliation_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reconciliation_id: Mapped[int] = mapped_column(
        ForeignKey("position_reconciliations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product: Mapped[str] = mapped_column(String(64), nullable=False)
    ticker: Mapped[str | None] = mapped_column(String(32), nullable=True)
    asset_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    institution: Mapped[str | None] = mapped_column(String(255), nullable=True)
    b3_quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    ledger_quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    resolution: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN")
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    reconciliation: Mapped[PositionReconciliationModel] = relationship(back_populates="lines")
