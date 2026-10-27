"""SQLAlchemy 2.0 ORM model of the tax rule registry (rates with validity periods)."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import JSON, Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from infra.data.db import Base


class TaxRuleModel(Base):
    """IR/IOF rates of a tax regime in force between `valid_from` and `valid_to`."""

    __tablename__ = "tax_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    regime: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    tax_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # [{"up_to_days": int | None, "rate": float}, ...] ordered by day limit (ADR 0006 fractions)
    brackets: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    legal_basis: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    description: Mapped[str] = mapped_column(String(400), nullable=False, default="")
