"""SQLAlchemy 2.0 ORM models of the CVM disclosures (Phase 28)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from infra.data.db import Base
from infra.data.models.common import utc_now


class CvmIssuerTickerModel(Base):
    """Trading code -> company CNPJ, from the FCA."""

    __tablename__ = "cvm_issuer_tickers"

    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    cnpj: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    reference_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CvmDocumentModel(Base):
    """One IPE document; the protocol is unique and a new version replaces the old one."""

    __tablename__ = "cvm_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    protocol: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    cnpj: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    cvm_code: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    category: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    doc_type: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    species: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    subject: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reference_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    link: Mapped[str] = mapped_column(Text, nullable=False, default="")
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CvmStatementFactModel(Base):
    """One value of a statement delivered to the CVM (DFP/ITR), per version (Phase 42.2)."""

    __tablename__ = "cvm_statements"
    __table_args__ = (
        Index("ix_cvm_statements_cnpj_delivered", "cnpj", "delivered_on"),
        Index("ix_cvm_statements_doc", "doc_type", "reference_date"),
    )

    cnpj: Mapped[str] = mapped_column(String(14), primary_key=True)
    doc_type: Mapped[str] = mapped_column(String(3), primary_key=True)
    reference_date: Mapped[date] = mapped_column(Date, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    metric: Mapped[str] = mapped_column(String(32), primary_key=True)
    delivered_on: Mapped[date] = mapped_column(Date, nullable=False)
    basis: Mapped[str] = mapped_column(String(3), nullable=False)
    template: Mapped[str] = mapped_column(String(10), nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)


class CvmStatementLoadModel(Base):
    """Which yearly CVM statement file was loaded, and from which version of the file."""

    __tablename__ = "cvm_statement_loads"

    doc_type: Mapped[str] = mapped_column(String(3), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_stamp: Mapped[str] = mapped_column(String(64), nullable=False)
    facts: Mapped[int] = mapped_column(Integer, nullable=False)
    loaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
