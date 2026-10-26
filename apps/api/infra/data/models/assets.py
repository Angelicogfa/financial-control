"""SQLAlchemy 2.0 ORM models: assets, fixed income terms and checklist answers/evaluations.

Table and column names are in English."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from domain.shared.enums import (
    ArcaClass,
    AssetType,
    default_arca_class,
    default_currency,
)
from infra.data.db import Base
from infra.data.models.common import utc_now

if TYPE_CHECKING:
    from infra.data.models.ledger import (
        CorporateEventModel,
        EarningModel,
        TransactionModel,
    )


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
    checklist_profile: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    purpose: Mapped[str] = mapped_column(String(24), nullable=False, default="ARCA")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
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
    corporate_events: Mapped[list[CorporateEventModel]] = relationship(
        "CorporateEventModel",
        cascade="all, delete-orphan",
        order_by="CorporateEventModel.ex_date.asc(), CorporateEventModel.id.asc()",
    )
    checklist_answers: Mapped[list[ChecklistAnswerModel]] = relationship(
        "ChecklistAnswerModel",
        cascade="all, delete-orphan",
        order_by="ChecklistAnswerModel.answered_at.asc(), ChecklistAnswerModel.id.asc()",
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


class ChecklistAnswerModel(Base):
    """Append-only checklist answers; the latest row per question is the current answer."""

    __tablename__ = "checklist_answers"
    __table_args__ = (
        Index("ix_checklist_answers_asset_question", "asset_id", "question_id", "answered_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[str] = mapped_column(String(48), nullable=False)
    value: Mapped[str | None] = mapped_column(String(4), nullable=True)
    source: Mapped[str] = mapped_column(String(8), nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    checklist_version: Mapped[int] = mapped_column(Integer, nullable=False, default=2)


class ChecklistEvaluationModel(Base):
    """History of checklist evaluations (score and coverage over time)."""

    __tablename__ = "checklist_evaluations"
    __table_args__ = (Index("ix_checklist_evaluations_asset_at", "asset_id", "evaluated_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    profile: Mapped[str] = mapped_column(String(16), nullable=False)
    checklist_version: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    normalized_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    coverage_pct: Mapped[float] = mapped_column(Float, nullable=False)
    answered: Mapped[int] = mapped_column(Integer, nullable=False)
    applicable: Mapped[int] = mapped_column(Integer, nullable=False)
    recommendation: Mapped[str] = mapped_column(String(16), nullable=False)
