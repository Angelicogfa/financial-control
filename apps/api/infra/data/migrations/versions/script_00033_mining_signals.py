"""Point-in-time signals of the Garimpo (Phase 43.2).

`mining_signals` keeps, per company and month, the VALUE, QUALITY, IMPROVEMENT and MOMENTUM
z-scores computed with only what was known that month; it is recomputed every week.

Revision ID: script_00033
Revises: script_00032
Create Date: 2026-10-30 18:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00033"
down_revision: str | None = "script_00032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mining_signals",
        sa.Column("ticker", sa.String(length=16), primary_key=True),
        sa.Column("month", sa.Date(), primary_key=True),
        sa.Column("signal", sa.String(length=16), primary_key=True),
        sa.Column("z", sa.Float(), nullable=False),
    )
    op.create_index("ix_mining_signals_month", "mining_signals", ["month"])


def downgrade() -> None:
    op.drop_index("ix_mining_signals_month", table_name="mining_signals")
    op.drop_table("mining_signals")
