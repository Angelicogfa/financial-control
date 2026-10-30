"""Findings of the weekly Garimpo runs (Phase 43.4).

`mining_findings` keeps each run's best scores with the signals and the reason, never rewritten
after the week: they are the base of the record (43.5).

Revision ID: script_00034
Revises: script_00033
Create Date: 2026-10-30 20:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00034"
down_revision: str | None = "script_00033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mining_findings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("found_on", sa.Date(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("trusted", sa.Boolean(), nullable=False),
        sa.Column("signals", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
    )
    op.create_index("ix_mining_findings_found_on", "mining_findings", ["found_on"])


def downgrade() -> None:
    op.drop_index("ix_mining_findings_found_on", table_name="mining_findings")
    op.drop_table("mining_findings")
