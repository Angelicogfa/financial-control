"""Daily catalog of listed B3 instruments for the screener and watchlist (item 11.6).

Revision ID: script_00012
Revises: script_00011
Create Date: 2026-10-25 00:30:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00012"
down_revision: str | None = "script_00011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "instrument_catalog",
        sa.Column("ticker", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("asset_type", sa.String(length=32), nullable=True),
        sa.Column("sector", sa.String(length=80), nullable=True),
        sa.Column("close", sa.Float(), nullable=True),
        sa.Column("change_pct", sa.Float(), nullable=True),
        sa.Column("volume_brl", sa.Float(), nullable=True),
        sa.Column("market_cap", sa.Float(), nullable=True),
        sa.Column("logo_url", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_instrument_catalog_asset_type", "instrument_catalog", ["asset_type"])


def downgrade() -> None:
    op.drop_index("ix_instrument_catalog_asset_type", table_name="instrument_catalog")
    op.drop_table("instrument_catalog")
