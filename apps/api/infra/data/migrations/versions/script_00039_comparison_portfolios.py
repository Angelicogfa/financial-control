"""Comparison portfolios of the live scoreboard (Phase 45.8a).

`comparison_portfolios` keeps, per strategy (and per random draw), the day it was created, the
book (units, cost, cash and totals, to resume) and the record of values: retroactive before the
creation, prospective from it on.

Revision ID: script_00039
Revises: script_00038
Create Date: 2026-11-01 15:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00039"
down_revision: str | None = "script_00038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "comparison_portfolios",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(32), nullable=False),
        sa.Column("variant", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("label", sa.String(64), nullable=False),
        sa.Column("created_on", sa.Date(), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("points", sa.JSON(), nullable=False),
        sa.UniqueConstraint("key", "variant", name="uq_comparison_portfolios_key"),
    )


def downgrade() -> None:
    op.drop_table("comparison_portfolios")
