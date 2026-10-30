"""Estimated layers of the price forecast and their gate (Phase 42.3).

`forecast_models` keeps each estimation of a layer (VALUATION now, EVENTS later): the effect,
its uncertainty, the out-of-sample result and whether it entered the forecast.

Revision ID: script_00032
Revises: script_00031
Create Date: 2026-10-30 14:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00032"
down_revision: str | None = "script_00031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "forecast_models",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_forecast_models_kind", "forecast_models", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_forecast_models_kind", table_name="forecast_models")
    op.drop_table("forecast_models")
