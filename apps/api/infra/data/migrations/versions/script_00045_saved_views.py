"""Saved views: named filters of the screener, the ledger and the portfolio (Phase 48.R9).

Additive only: a new table. The filters were kept in sessionStorage alone until now.

Revision ID: script_00045
Revises: script_00044
Create Date: 2026-11-02 23:30:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00045"
down_revision: str | None = "script_00044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "saved_views",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scope", sa.String(24), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("scope", "name", name="uq_saved_views_scope_name"),
    )


def downgrade() -> None:
    op.drop_table("saved_views")
