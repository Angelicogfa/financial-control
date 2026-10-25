"""Persisted contribution plans: draft, confirmed (with its trades) or discarded (item 12.1).

Revision ID: script_00013
Revises: script_00012
Create Date: 2026-10-25 02:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00013"
down_revision: str | None = "script_00012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contribution_plans",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("amount_brl", sa.Numeric(20, 2), nullable=False),
        sa.Column("strategy_override", sa.String(length=24), nullable=True),
        sa.Column("policy_version", sa.Integer(), nullable=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("transaction_ids", sa.JSON(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discarded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_contribution_plans_status", "contribution_plans", ["status"])


def downgrade() -> None:
    op.drop_index("ix_contribution_plans_status", table_name="contribution_plans")
    op.drop_table("contribution_plans")
