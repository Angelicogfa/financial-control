"""Daily catalog of Brazilian Treasury bonds (Tesouro Direto) from Tesouro Transparente.

Revision ID: script_00018
Revises: script_00017
Create Date: 2026-10-26 22:50:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00018"
down_revision: str | None = "script_00017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "treasury_catalog",
        sa.Column("symbol", sa.String(length=80), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("bond_type", sa.String(length=120), nullable=False),
        sa.Column("instrument_kind", sa.String(length=32), nullable=False),
        sa.Column("indexer", sa.String(length=16), nullable=False),
        sa.Column("raw_indexer", sa.String(length=32), nullable=False),
        sa.Column("coupon_type", sa.String(length=32), nullable=False),
        sa.Column("maturity_date", sa.Date(), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column("base_date", sa.Date(), nullable=True),
        sa.Column("buy_rate", sa.Float(), nullable=True),
        sa.Column("sell_rate", sa.Float(), nullable=True),
        sa.Column("buy_price", sa.Float(), nullable=True),
        sa.Column("sell_price", sa.Float(), nullable=True),
        sa.Column("base_price", sa.Float(), nullable=True),
        sa.Column("rate_type", sa.String(length=64), nullable=True),
        sa.Column("rate_unit", sa.String(length=32), nullable=True),
        sa.Column("rate_description", sa.String(length=255), nullable=True),
        sa.Column("contracted_rate_percent", sa.Float(), nullable=False),
        sa.Column("liquidity", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_treasury_catalog_indexer", "treasury_catalog", ["indexer"])
    op.create_index("ix_treasury_catalog_maturity_date", "treasury_catalog", ["maturity_date"])


def downgrade() -> None:
    op.drop_index("ix_treasury_catalog_maturity_date", table_name="treasury_catalog")
    op.drop_index("ix_treasury_catalog_indexer", table_name="treasury_catalog")
    op.drop_table("treasury_catalog")
