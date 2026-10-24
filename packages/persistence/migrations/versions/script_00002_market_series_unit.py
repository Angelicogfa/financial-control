"""Store the unit of every market series point (ADR 0006, finding C-01).

Existing rows are tagged from their symbol: BCB CDI/SELIC are percent per business day,
IPCA is percent per month, benchmark indices are index points and anything else is a price.

Revision ID: script_00002
Revises: script_00001
Create Date: 2026-10-24 18:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00002"
down_revision: str | None = "script_00001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("market_series") as batch:
        batch.add_column(sa.Column("unit", sa.String(length=24), nullable=True))

    op.execute(
        """
        UPDATE market_series SET unit = CASE
            WHEN symbol IN ('CDI', 'SELIC') THEN 'PERCENT_PER_DAY'
            WHEN symbol = 'IPCA' THEN 'PERCENT_PER_MONTH'
            WHEN symbol IN ('IBOV', 'IFIX', 'SP500') THEN 'INDEX_POINTS'
            ELSE 'PRICE'
        END
        """
    )

    with op.batch_alter_table("market_series") as batch:
        batch.alter_column("unit", existing_type=sa.String(length=24), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("market_series") as batch:
        batch.drop_column("unit")
