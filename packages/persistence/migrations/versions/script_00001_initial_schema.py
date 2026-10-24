"""Initial schema for Financial Control (assets, fixed_income_terms, transactions, earnings, etc.).

Revision ID: script_00001
Revises: None
Create Date: 2026-10-24 11:38:00
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

revision: str = "script_00001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("arca_class", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="BRL"),
        sa.Column("manual_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("custom_class_weight", sa.Numeric(8, 4), nullable=True),
        sa.Column("use_cerrado", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("cerrado_answers", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "manual_price IS NULL OR manual_price >= 0", name="ck_assets_manual_price"
        ),
        sa.CheckConstraint(
            "custom_class_weight IS NULL OR custom_class_weight >= 0",
            name="ck_assets_custom_weight",
        ),
        sa.UniqueConstraint("ticker", name="uq_assets_ticker"),
    )
    op.create_index("ix_assets_ticker", "assets", ["ticker"], unique=True)
    op.create_index("ix_assets_asset_type", "assets", ["asset_type"])
    op.create_index("ix_assets_arca_class", "assets", ["arca_class"])
    op.create_index("ix_assets_is_active", "assets", ["is_active"])

    op.create_table(
        "fixed_income_terms",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "asset_id",
            sa.Integer(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("instrument_kind", sa.String(length=32), nullable=False),
        sa.Column("indexer", sa.String(length=16), nullable=False),
        sa.Column("contracted_rate", sa.Numeric(12, 6), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("maturity_date", sa.Date(), nullable=True),
        sa.Column("tax_exempt", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("liquidity", sa.String(length=24), nullable=False, server_default="AT_MATURITY"),
        sa.Column("issuer", sa.String(length=120), nullable=True),
        sa.CheckConstraint("contracted_rate >= 0", name="ck_fixed_income_terms_rate_non_negative"),
    )

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "asset_id",
            sa.Integer(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("fees", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("fx_rate", sa.Numeric(14, 6), nullable=False, server_default="1"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_transactions_quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_transactions_unit_price_non_negative"),
        sa.CheckConstraint("fees >= 0", name="ck_transactions_fees_non_negative"),
        sa.CheckConstraint("fx_rate > 0", name="ck_transactions_fx_rate_positive"),
    )
    op.create_index("ix_transactions_asset_id", "transactions", ["asset_id"])
    op.create_index("ix_transactions_kind", "transactions", ["kind"])
    op.create_index("ix_transactions_trade_date", "transactions", ["trade_date"])
    op.create_index("ix_transactions_asset_trade_date", "transactions", ["asset_id", "trade_date"])

    op.create_table(
        "earnings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "asset_id",
            sa.Integer(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("ex_date", sa.Date(), nullable=True),
        sa.Column("gross_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("withholding_tax", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("net_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("gross_amount > 0", name="ck_earnings_gross_positive"),
        sa.CheckConstraint("withholding_tax >= 0", name="ck_earnings_tax_non_negative"),
        sa.CheckConstraint("net_amount >= 0", name="ck_earnings_net_non_negative"),
    )
    op.create_index("ix_earnings_asset_id", "earnings", ["asset_id"])
    op.create_index("ix_earnings_kind", "earnings", ["kind"])
    op.create_index("ix_earnings_payment_date", "earnings", ["payment_date"])
    op.create_index("ix_earnings_asset_payment_date", "earnings", ["asset_id", "payment_date"])

    arca_targets_table = op.create_table(
        "arca_targets",
        sa.Column("arca_class", sa.String(length=32), primary_key=True),
        sa.Column("target_pct", sa.Numeric(6, 2), nullable=False),
        sa.Column(
            "intra_class_strategy",
            sa.String(length=24),
            nullable=False,
            server_default="CERRADO",
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "target_pct >= 0 AND target_pct <= 100", name="ck_arca_targets_pct_bounds"
        ),
    )

    now = datetime.now(UTC)
    op.bulk_insert(
        arca_targets_table,
        [
            {
                "arca_class": "ACOES",
                "target_pct": Decimal("25.00"),
                "intra_class_strategy": "CERRADO",
                "updated_at": now,
            },
            {
                "arca_class": "REAL_ESTATE",
                "target_pct": Decimal("25.00"),
                "intra_class_strategy": "CERRADO",
                "updated_at": now,
            },
            {
                "arca_class": "CAIXA",
                "target_pct": Decimal("25.00"),
                "intra_class_strategy": "EQUAL_WEIGHT",
                "updated_at": now,
            },
            {
                "arca_class": "ATIVOS_INTERNACIONAIS",
                "target_pct": Decimal("25.00"),
                "intra_class_strategy": "CERRADO",
                "updated_at": now,
            },
        ],
    )

    op.create_table(
        "market_series",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("reference_date", sa.Date(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.UniqueConstraint("symbol", "reference_date", name="uq_market_series_symbol_date"),
    )
    op.create_index("ix_market_series_symbol", "market_series", ["symbol"])
    op.create_index("ix_market_series_reference_date", "market_series", ["reference_date"])

    op.create_table(
        "portfolio_snapshots",
        sa.Column("snapshot_date", sa.Date(), primary_key=True),
        sa.Column("invested_value", sa.Float(), nullable=False),
        sa.Column("market_value", sa.Float(), nullable=False),
        sa.Column("unrealized_pnl", sa.Float(), nullable=False),
        sa.Column("realized_pnl_cum", sa.Float(), nullable=False, server_default="0"),
        sa.Column("earnings_cum", sa.Float(), nullable=False, server_default="0"),
        sa.Column("consolidated_pnl", sa.Float(), nullable=False, server_default="0"),
        sa.Column("net_flow", sa.Float(), nullable=False, server_default="0"),
        sa.Column("by_class", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("portfolio_snapshots")
    op.drop_index("ix_market_series_reference_date", table_name="market_series")
    op.drop_index("ix_market_series_symbol", table_name="market_series")
    op.drop_table("market_series")
    op.drop_table("arca_targets")
    op.drop_index("ix_earnings_asset_payment_date", table_name="earnings")
    op.drop_index("ix_earnings_payment_date", table_name="earnings")
    op.drop_index("ix_earnings_kind", table_name="earnings")
    op.drop_index("ix_earnings_asset_id", table_name="earnings")
    op.drop_table("earnings")
    op.drop_index("ix_transactions_asset_trade_date", table_name="transactions")
    op.drop_index("ix_transactions_trade_date", table_name="transactions")
    op.drop_index("ix_transactions_kind", table_name="transactions")
    op.drop_index("ix_transactions_asset_id", table_name="transactions")
    op.drop_table("transactions")
    op.drop_table("fixed_income_terms")
    op.drop_index("ix_assets_is_active", table_name="assets")
    op.drop_index("ix_assets_arca_class", table_name="assets")
    op.drop_index("ix_assets_asset_type", table_name="assets")
    op.drop_index("ix_assets_ticker", table_name="assets")
    op.drop_table("assets")
