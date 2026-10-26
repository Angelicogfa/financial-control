"""SQLAlchemy 2.0 ORM models: market series, fundamentals and the B3 catalog.

Table and column names are in English."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from fincontrol_persistence.core.db import Base
from fincontrol_persistence.models.common import utc_now


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


class FundamentalSnapshotModel(Base):
    """Yearly (or TTM) statement figures of a ticker; metrics follow `METRIC_KEYS`."""

    __tablename__ = "fundamental_snapshots"
    __table_args__ = (
        UniqueConstraint("ticker", "reference_date", "period", name="uq_fundamental_snapshots_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reference_date: Mapped[date] = mapped_column(Date, nullable=False)
    period: Mapped[str] = mapped_column(String(8), nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class InstrumentCatalogModel(Base):
    """Listed B3 instruments refreshed daily; feeds the screener and the watchlist."""

    __tablename__ = "instrument_catalog"

    ticker: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    asset_type: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    sector: Mapped[str | None] = mapped_column(String(80), nullable=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_brl: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
