"""Store the last quote and fundamentals of each ticker (Phase 38).

The worker writes `market_data` and the screens read it, so a page never waits for a market
data provider. One row per ticker, with the quote and the fundamentals fetched apart.

Revision ID: script_00026
Revises: script_00025
Create Date: 2026-10-29 16:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00026"
down_revision: str | None = "script_00025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_data",
        sa.Column("ticker", sa.String(length=32), primary_key=True),
        sa.Column("quote", sa.JSON(), nullable=True),
        sa.Column("quote_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fundamentals", sa.JSON(), nullable=True),
        sa.Column("fundamentals_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("market_data")
