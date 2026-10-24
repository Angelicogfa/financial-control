"""Yearly statement history per ticker for the fundamentalist checklist (item 11.1).

Revision ID: script_00010
Revises: script_00009
Create Date: 2026-10-24 22:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00010"
down_revision: str | None = "script_00009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fundamental_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("reference_date", sa.Date(), nullable=False),
        sa.Column("period", sa.String(length=8), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "ticker", "reference_date", "period", name="uq_fundamental_snapshots_key"
        ),
    )
    op.create_index("ix_fundamental_snapshots_ticker", "fundamental_snapshots", ["ticker"])


def downgrade() -> None:
    op.drop_index("ix_fundamental_snapshots_ticker", table_name="fundamental_snapshots")
    op.drop_table("fundamental_snapshots")
