"""SQLAlchemy 2.0 ORM models: worker job runs.

Table and column names are in English."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from infra.data.db import Base


class JobRunModel(Base):
    """Execution log of background worker jobs."""

    __tablename__ = "job_runs"
    __table_args__ = (Index("ix_job_runs_job_started", "job_name", "started_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class WorkerRequestErrorModel(Base):
    """Detailed log of failed external provider requests made by the worker."""

    __tablename__ = "worker_request_errors"
    __table_args__ = (
        Index("ix_worker_request_errors_occurred_at", "occurred_at"),
        Index("ix_worker_request_errors_resolved_at", "resolved_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    job_name: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str] = mapped_column(String(128), nullable=False)
    request_url: Mapped[str] = mapped_column(String(512), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_type: Mapped[str] = mapped_column(String(64), nullable=False)
    error_detail: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
