"""Lenses and gates of the recommendation (Phases 45.1 and 45.2).

`asset_lenses` keeps, per weekly run, the eight lenses of every asset of the universe (portfolio,
watchlist and the Garimpo's liquid stocks): value, value on [0, 1], confidence, sentence and
highlights. `asset_gates` keeps, per run, each gate's outcome (PASS, FAIL, WARN or
NOT_APPLICABLE) with its reason. The point-in-time signals stay in `mining_signals`, which now
also holds INCOME and RISK; no change to it is needed.

Revision ID: script_00036
Revises: script_00035
Create Date: 2026-10-31 10:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00036"
down_revision: str | None = "script_00035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "asset_lenses",
        sa.Column("as_of", sa.Date(), primary_key=True),
        sa.Column("ticker", sa.String(length=16), primary_key=True),
        sa.Column("lens", sa.String(length=16), primary_key=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("arca_class", sa.String(length=32), nullable=True),
        sa.Column("sector", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("signal_ticker", sa.String(length=16), nullable=True),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("normalized", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("flags", sa.JSON(), nullable=False),
    )
    op.create_index("ix_asset_lenses_as_of", "asset_lenses", ["as_of"])
    op.create_table(
        "asset_gates",
        sa.Column("as_of", sa.Date(), primary_key=True),
        sa.Column("ticker", sa.String(length=16), primary_key=True),
        sa.Column("gate", sa.String(length=16), primary_key=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
    )
    op.create_index("ix_asset_gates_as_of", "asset_gates", ["as_of"])


def downgrade() -> None:
    op.drop_index("ix_asset_gates_as_of", table_name="asset_gates")
    op.drop_table("asset_gates")
    op.drop_index("ix_asset_lenses_as_of", table_name="asset_lenses")
    op.drop_table("asset_lenses")
