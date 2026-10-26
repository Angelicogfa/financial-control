"""SQLAlchemy 2.0 ORM models: alert dismissals.

Table and column names are in English."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from infra.data.db import Base
from infra.data.models.common import utc_now


class AlertDismissalModel(Base):
    """Hidden alert keys; `until` NULL hides it while the condition persists."""

    __tablename__ = "alert_dismissals"

    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    dismissed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    until: Mapped[date | None] = mapped_column(Date, nullable=True)
