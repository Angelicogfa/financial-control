"""SQLAlchemy 2.0 ORM models for Financial Control.

All table names, column names, constraints, and comments are strictly in English.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fincontrol_core.domain.enums import (
    ArcaClass,
    AssetType,
    default_arca_class,
    default_currency,
)
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fincontrol_persistence.db import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AssetModel(Base):
    """Registered financial asset (variable income, fixed income, international, or crypto)."""

    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint("manual_price IS NULL OR manual_price >= 0", name="ck_assets_manual_price"),
        CheckConstraint(
            "custom_class_weight IS NULL OR custom_class_weight >= 0",
            name="ck_assets_custom_weight",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    arca_class: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="BRL")
    manual_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    custom_class_weight: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    use_cerrado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    cerrado_answers: Mapped[dict[str, bool]] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    purpose: Mapped[str] = mapped_column(String(24), nullable=False, default="ARCA")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )

    fixed_income_term: Mapped[FixedIncomeTermModel | None] = relationship(
        "FixedIncomeTermModel",
        back_populates="asset",
        uselist=False,
        cascade="all, delete-orphan",
    )
    transactions: Mapped[list[TransactionModel]] = relationship(
        "TransactionModel",
        back_populates="asset",
        cascade="all, delete-orphan",
        order_by="TransactionModel.trade_date.asc(), TransactionModel.id.asc()",
    )
    earnings: Mapped[list[EarningModel]] = relationship(
        "EarningModel",
        back_populates="asset",
        cascade="all, delete-orphan",
        order_by="EarningModel.payment_date.asc(), EarningModel.id.asc()",
    )

    @classmethod
    def create(
        cls,
        *,
        ticker: str,
        name: str,
        asset_type: AssetType | str,
        arca_class: ArcaClass | str | None = None,
        currency: str | None = None,
        manual_price: Decimal | None = None,
        custom_class_weight: Decimal | None = None,
        use_cerrado: bool = True,
        cerrado_answers: dict[str, bool] | None = None,
        is_active: bool = True,
        notes: str | None = None,
    ) -> AssetModel:
        resolved_type = AssetType(asset_type)
        resolved_arca = ArcaClass(arca_class) if arca_class else default_arca_class(resolved_type)
        resolved_currency = (currency or default_currency(resolved_type)).upper()
        return cls(
            ticker=ticker.strip().upper(),
            name=name.strip(),
            asset_type=resolved_type.value,
            arca_class=resolved_arca.value,
            currency=resolved_currency,
            manual_price=manual_price,
            custom_class_weight=custom_class_weight,
            use_cerrado=use_cerrado,
            cerrado_answers=dict(cerrado_answers or {}),
            is_active=is_active,
            notes=notes,
        )


class FixedIncomeTermModel(Base):
    """Contract parameters for automatic fixed income curve calculation (CDI, IPCA+, Pre, SELIC)."""

    __tablename__ = "fixed_income_terms"
    __table_args__ = (
        CheckConstraint("contracted_rate >= 0", name="ck_fixed_income_terms_rate_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("assets.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    instrument_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    indexer: Mapped[str] = mapped_column(String(16), nullable=False)
    contracted_rate: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    maturity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    tax_exempt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    liquidity: Mapped[str] = mapped_column(String(24), nullable=False, default="AT_MATURITY")
    issuer: Mapped[str | None] = mapped_column(String(120), nullable=True)

    asset: Mapped[AssetModel] = relationship("AssetModel", back_populates="fixed_income_term")


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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )

    asset: Mapped[AssetModel] = relationship("AssetModel", back_populates="earnings")


class InvestmentPolicyModel(Base):
    """Append-only versions of the investment policy (ARCA, eligibility, valuation rules)."""

    __tablename__ = "investment_policies"

    version: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    arca: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    eligibility: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    valuation: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class MarketSeriesModel(Base):
    """Historical price and macroeconomic index series (^BVSP, IFIX.SA, ^GSPC, CDI, IPCA)."""

    __tablename__ = "market_series"
    __table_args__ = (
        UniqueConstraint("symbol", "reference_date", name="uq_market_series_symbol_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reference_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(24), nullable=False)


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


class JobRunModel(Base):
    """Execution log of background worker jobs."""

    __tablename__ = "job_runs"
    __table_args__ = (Index("ix_job_runs_job_started", "job_name", "started_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
