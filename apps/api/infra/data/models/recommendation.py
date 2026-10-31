"""SQLAlchemy 2.0 ORM models of the recommendation (Phase 45)."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import JSON, Date, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from infra.data.db import Base


class AssetLensModel(Base):
    """One lens of one asset in a weekly run (Phase 45.1)."""

    __tablename__ = "asset_lenses"
    __table_args__ = (Index("ix_asset_lenses_as_of", "as_of"),)

    as_of: Mapped[date] = mapped_column(Date, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    lens: Mapped[str] = mapped_column(String(16), primary_key=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    arca_class: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sector: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    signal_ticker: Mapped[str | None] = mapped_column(String(16), nullable=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    normalized: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    flags: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)


class AssetGateModel(Base):
    """One gate of one asset in a weekly run (Phase 45.2)."""

    __tablename__ = "asset_gates"
    __table_args__ = (Index("ix_asset_gates_as_of", "as_of"),)

    as_of: Mapped[date] = mapped_column(Date, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    gate: Mapped[str] = mapped_column(String(16), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)


class RecommendationMatrixModel(Base):
    """The decision matrix of one ARCA class in a weekly run (Phase 45.3)."""

    __tablename__ = "recommendation_matrices"

    as_of: Mapped[date] = mapped_column(Date, primary_key=True)
    arca_class: Mapped[str] = mapped_column(String(32), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    construction: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class RecommendationRunModel(Base):
    """One weekly run of the recommendation (Phase 45.5): the entry of its history."""

    __tablename__ = "recommendation_runs"

    as_of: Mapped[date] = mapped_column(Date, primary_key=True)
    policy_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    signal_month: Mapped[date | None] = mapped_column(Date, nullable=True)
    assets: Mapped[int] = mapped_column(Integer, nullable=False)
    eligible: Mapped[int] = mapped_column(Integer, nullable=False)
    selected: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
