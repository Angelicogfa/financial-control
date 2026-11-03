"""SQLAlchemy 2.0 ORM model of the saved views (Phase 48.R9)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from infra.data.db import Base


class SavedViewModel(Base):
    """Named filters of a screen; the name is unique within the screen."""

    __tablename__ = "saved_views"
    __table_args__ = (UniqueConstraint("scope", "name", name="uq_saved_views_scope_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(24), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
