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

from infra.data.db import Base
from infra.data.models.common import utc_now


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
    first_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=utc_now
    )


class MarketDataModel(Base):
    """Last quote and fundamentals of a ticker as the worker fetched them (Phase 38).

    `quote` and `fundamentals` hold the provider-neutral payloads (`Quote.to_dict()`,
    `Fundamentals.to_dict()`); each has its own fetch time because they refresh apart.
    """

    __tablename__ = "market_data"

    ticker: Mapped[str] = mapped_column(String(32), primary_key=True)
    quote: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    quote_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fundamentals: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    fundamentals_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
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


class TreasuryCatalogModel(Base):
    """Brazilian Treasury bonds (Tesouro Direto) synced daily from Tesouro Transparente."""

    __tablename__ = "treasury_catalog"

    symbol: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    bond_type: Mapped[str] = mapped_column(String(120), nullable=False)
    instrument_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    indexer: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    raw_indexer: Mapped[str] = mapped_column(String(32), nullable=False)
    coupon_type: Mapped[str] = mapped_column(String(32), nullable=False)
    maturity_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    buy_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    sell_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    buy_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    sell_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    base_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    rate_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rate_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rate_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contracted_rate_percent: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    liquidity: Mapped[str] = mapped_column(String(32), nullable=False, default="DAILY")
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
