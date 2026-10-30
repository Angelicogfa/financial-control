"""SQLAlchemy 2.0 ORM models of the Garimpo (Phase 43)."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import JSON, Boolean, Date, Float, Index, Integer, String, Text
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


class MiningFindingModel(Base):
    """A finding of a weekly Garimpo run (Phase 43.4); the base of the record (43.5)."""

    __tablename__ = "mining_findings"
    __table_args__ = (Index("ix_mining_findings_found_on", "found_on"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    found_on: Mapped[date] = mapped_column(Date, nullable=False)
    month: Mapped[date] = mapped_column(Date, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    trusted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    signals: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
