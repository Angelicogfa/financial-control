"""Store portfolio snapshot money columns as Numeric(20, 2) instead of Float (finding D-02).

Revision ID: script_00005
Revises: script_00004
Create Date: 2026-10-24 18:30:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00005"
down_revision: str | None = "script_00004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY_COLUMNS = (
    "invested_value",
    "market_value",
    "unrealized_pnl",
    "realized_pnl_cum",
    "earnings_cum",
    "consolidated_pnl",
    "net_flow",
)


def upgrade() -> None:
    with op.batch_alter_table("portfolio_snapshots") as batch:
        for column in MONEY_COLUMNS:
            batch.alter_column(
                column,
                existing_type=sa.Float(),
                type_=sa.Numeric(20, 2),
                existing_nullable=False,
            )


def downgrade() -> None:
    with op.batch_alter_table("portfolio_snapshots") as batch:
        for column in MONEY_COLUMNS:
            batch.alter_column(
                column,
                existing_type=sa.Numeric(20, 2),
                type_=sa.Float(),
                existing_nullable=False,
            )
