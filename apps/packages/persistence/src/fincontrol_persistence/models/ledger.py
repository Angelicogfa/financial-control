"""SQLAlchemy 2.0 ORM models: transactions, earnings, corporate events and B3 import dedup.

Table and column names are in English."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fincontrol_persistence.core.db import Base
from fincontrol_persistence.models.common import utc_now

if TYPE_CHECKING:
    from fincontrol_persistence.models.assets import AssetModel


class TransactionModel(Base):
    """Buy and sell trade ledger entry."""

    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_transactions_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_transactions_unit_price_non_negative"),
        CheckConstraint("fees >= 0", name="ck_transactions_fees_non_negative"),
        CheckConstraint("fx_rate > 0", name="ck_transactions_fx_rate_positive"),
        Index("ix_transactions_asset_trade_date", "asset_id", "trade_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    fees: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"))
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False, default=Decimal("1"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id"), nullable=False, index=True
    )
    import_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    asset: Mapped[AssetModel] = relationship("AssetModel", back_populates="transactions")


class EarningModel(Base):
    """Received earnings/distributions (dividends, JCP, FII yields, fixed income coupons)."""

    __tablename__ = "earnings"
    __table_args__ = (
        CheckConstraint("gross_amount > 0", name="ck_earnings_gross_positive"),
        CheckConstraint("withholding_tax >= 0", name="ck_earnings_tax_non_negative"),
        CheckConstraint("net_amount >= 0", name="ck_earnings_net_non_negative"),
        CheckConstraint("fx_rate > 0", name="ck_earnings_fx_rate_positive"),
        Index("ix_earnings_asset_payment_date", "asset_id", "payment_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    ex_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    withholding_tax: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0")
    )
    net_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False, default=Decimal("1"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id"), nullable=False, index=True
    )
    import_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    asset: Mapped[AssetModel] = relationship("AssetModel", back_populates="earnings")


class CorporateEventModel(Base):
    """Split, reverse split or bonus issue of an asset (item 12.4)."""

    __tablename__ = "corporate_events"
    __table_args__ = (
        CheckConstraint("factor > 0", name="ck_corporate_events_factor_positive"),
        CheckConstraint("unit_cost >= 0", name="ck_corporate_events_unit_cost"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    ex_date: Mapped[date] = mapped_column(Date, nullable=False)
    factor: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    import_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
