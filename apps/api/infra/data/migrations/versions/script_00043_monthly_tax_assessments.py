"""Monthly income tax assessment of stock exchange gains (Phase 48.R7, TD-04).

`monthly_tax_assessments` keeps, per month and category (COMMON, DAY_TRADE, FII and the
TOTAL with the DARF), the figures last computed from the ledger and the day the DARF was
paid. Additive only.

Revision ID: script_00043
Revises: script_00042
Create Date: 2026-11-02 21:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00043"
down_revision: str | None = "script_00042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    money = sa.Numeric(18, 2)
    op.create_table(
        "monthly_tax_assessments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("sales_brl", money, nullable=False),
        sa.Column("result_brl", money, nullable=False),
        sa.Column("loss_out_brl", money, nullable=False),
        sa.Column("taxable_brl", money, nullable=False),
        sa.Column("tax_brl", money, nullable=False),
        sa.Column("darf_brl", money, nullable=False, server_default="0"),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=True),
        sa.UniqueConstraint("month", "category", name="uq_monthly_tax_assessments_month"),
    )
    op.create_index("ix_monthly_tax_assessments_month", "monthly_tax_assessments", ["month"])


def downgrade() -> None:
    op.drop_index("ix_monthly_tax_assessments_month", table_name="monthly_tax_assessments")
    op.drop_table("monthly_tax_assessments")
