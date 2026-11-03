"""Alert rules of the investor on any ticker (Phase 48.R6).

`alert_rules` keeps the condition (ticker, metric, operator, threshold) and what the worker
read last (value, when, and when it became true). Additive only.

Revision ID: script_00041
Revises: script_00040
Create Date: 2026-11-02 18:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00041"
down_revision: str | None = "script_00040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("metric", sa.String(32), nullable=False),
        sa.Column("operator", sa.String(8), nullable=False),
        sa.Column("threshold", sa.Numeric(24, 8), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_value", sa.Numeric(24, 8), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_alert_rules_ticker", "alert_rules", ["ticker"])


def downgrade() -> None:
    op.drop_index("ix_alert_rules_ticker", table_name="alert_rules")
    op.drop_table("alert_rules")
