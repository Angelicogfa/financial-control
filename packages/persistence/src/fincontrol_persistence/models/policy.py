"""SQLAlchemy 2.0 ORM models: versioned investment policy.

Table and column names are in English."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Integer,
)
from sqlalchemy.orm import Mapped, mapped_column

from fincontrol_persistence.core.db import Base
from fincontrol_persistence.models.common import utc_now


class InvestmentPolicyModel(Base):
    """Append-only versions of the investment policy (ARCA, eligibility, valuation rules)."""

    __tablename__ = "investment_policies"

    version: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    arca: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    eligibility: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    valuation: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
