"""Persist the remaining market sources the screens showed live (Phase 39).

- `market_data` also keeps the declared distributions of each ticker and when its full price
  history was first loaded;
- `market_quote_history`: the last quote of each ticker per day, an audit trail of the quotes;
- `asset_price_history`: daily OHLCV of each ticker, loaded in full once and extended daily.

Both new tables are keyed by (ticker, day), so every read by ticker and period uses the key.

Revision ID: script_00027
Revises: script_00026
Create Date: 2026-10-29 19:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00027"
down_revision: str | None = "script_00026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("market_data") as batch:
        batch.add_column(sa.Column("distributions", sa.JSON(), nullable=True))
        batch.add_column(
            sa.Column("distributions_fetched_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(sa.Column("history_loaded_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "market_quote_history",
        sa.Column("ticker", sa.String(length=32), primary_key=True),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("freshness", sa.String(length=16), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "asset_price_history",
        sa.Column("ticker", sa.String(length=32), primary_key=True),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("open", sa.Float(), nullable=True),
        sa.Column("high", sa.Float(), nullable=True),
        sa.Column("low", sa.Float(), nullable=True),
        sa.Column("adj_close", sa.Float(), nullable=True),
        sa.Column("volume", sa.Float(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("asset_price_history")
    op.drop_table("market_quote_history")
    with op.batch_alter_table("market_data") as batch:
        batch.drop_column("history_loaded_at")
        batch.drop_column("distributions_fetched_at")
        batch.drop_column("distributions")
