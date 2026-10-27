"""Detailed log of failed external provider requests made by background worker jobs.

Revision ID: script_00017
Revises: script_00016
Create Date: 2026-10-26 21:30:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00017"
down_revision: str | None = "script_00016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_request_errors",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_run_id", sa.Integer(), nullable=True),
        sa.Column("job_name", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=128), nullable=False),
        sa.Column("request_url", sa.String(length=512), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.String(length=64), nullable=False),
        sa.Column("error_detail", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_worker_request_errors_occurred_at",
        "worker_request_errors",
        ["occurred_at"],
    )
    op.create_index(
        "ix_worker_request_errors_resolved_at",
        "worker_request_errors",
        ["resolved_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_worker_request_errors_resolved_at", table_name="worker_request_errors")
    op.drop_index("ix_worker_request_errors_occurred_at", table_name="worker_request_errors")
    op.drop_table("worker_request_errors")
