"""Fixed income terms: optional informational issue date and the semiannual coupon flag.

Lots accrue from their own trade dates, so `issue_date` no longer drives the valuation and
becomes optional. `semiannual_coupons` marks bonds that pay Juros Semestrais (no rate can be
implied from their price); existing Tesouro bonds are backfilled from the asset name.

Revision ID: script_00020
Revises: script_00019
Create Date: 2026-10-27 18:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00020"
down_revision: str | None = "script_00019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("fixed_income_terms") as batch:
        batch.alter_column("issue_date", existing_type=sa.Date(), nullable=True)
        batch.add_column(
            sa.Column("semiannual_coupons", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    op.execute(
        """
        UPDATE fixed_income_terms SET semiannual_coupons = TRUE
        WHERE asset_id IN (
            SELECT id FROM assets WHERE lower(name) LIKE '%juros semestrais%'
        )
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("fixed_income_terms") as batch:
        batch.drop_column("semiannual_coupons")
    op.execute(
        """
        UPDATE fixed_income_terms SET issue_date = (
            SELECT min(t.trade_date) FROM transactions t
            WHERE t.asset_id = fixed_income_terms.asset_id
        )
        WHERE issue_date IS NULL
        """
    )
    op.execute("UPDATE fixed_income_terms SET issue_date = CURRENT_DATE WHERE issue_date IS NULL")
    with op.batch_alter_table("fixed_income_terms") as batch:
        batch.alter_column("issue_date", existing_type=sa.Date(), nullable=False)
