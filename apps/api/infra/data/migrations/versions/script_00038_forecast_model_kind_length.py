"""Widen `forecast_models.kind` to 32 characters (Phase 45.6 fix).

`RECOMMENDATION_BACKTEST` has 23 characters and did not fit in VARCHAR(16): PostgreSQL refused
the weekly past test of the recommendation (SQLite, used by the tests, does not check lengths).

Revision ID: script_00038
Revises: script_00037
Create Date: 2026-11-01 10:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00038"
down_revision: str | None = "script_00037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("forecast_models") as batch:
        batch.alter_column(
            "kind", type_=sa.String(32), existing_type=sa.String(16), existing_nullable=False
        )


def downgrade() -> None:
    with op.batch_alter_table("forecast_models") as batch:
        batch.alter_column(
            "kind", type_=sa.String(16), existing_type=sa.String(32), existing_nullable=False
        )
