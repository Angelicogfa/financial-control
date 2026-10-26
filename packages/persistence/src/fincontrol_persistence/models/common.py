"""SQLAlchemy 2.0 ORM models: helpers shared by several features.

Table and column names are in English."""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)
