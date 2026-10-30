"""SQLAlchemy 2.0 ORM models of the Garimpo (Phase 43)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from infra.data.db import Base


class MiningSignalModel(Base):
    """A point-in-time signal of a company in a month (Phase 43.2)."""

    __tablename__ = "mining_signals"
    __table_args__ = (Index("ix_mining_signals_month", "month"),)

    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    month: Mapped[date] = mapped_column(Date, primary_key=True)
    signal: Mapped[str] = mapped_column(String(16), primary_key=True)
    z: Mapped[float] = mapped_column(Float, nullable=False)
