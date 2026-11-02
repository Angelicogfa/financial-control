"""Goals of Planejar: wealth or monthly passive income by a date (Phase 48.R8).

Additive only: a new table, with the assumptions (return and income yield) kept per goal.

Revision ID: script_00044
Revises: script_00043
Create Date: 2026-11-02 23:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00044"
down_revision: str | None = "script_00043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "goals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("target_brl", sa.Numeric(18, 2), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("monthly_contribution_brl", sa.Numeric(18, 2), nullable=False),
        sa.Column("annual_return", sa.Numeric(8, 6), nullable=False),
        sa.Column("income_yield", sa.Numeric(8, 6), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("goals")
