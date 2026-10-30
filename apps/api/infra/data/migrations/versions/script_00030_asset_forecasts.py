"""Probabilistic price forecasts of the assets and their calibration (Phase 42.1).

`asset_forecasts` keeps one forecast per ticker and day (keyed by both, the earlier days stay
for audit); `forecast_calibrations` keeps each rolling-origin calibration.

Revision ID: script_00030
Revises: script_00029
Create Date: 2026-10-30 14:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00030"
down_revision: str | None = "script_00029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "asset_forecasts",
        sa.Column("ticker", sa.String(length=32), primary_key=True),
        sa.Column("as_of", sa.Date(), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("model_version", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "forecast_calibrations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_forecast_calibrations_as_of", "forecast_calibrations", ["as_of"])


def downgrade() -> None:
    op.drop_index("ix_forecast_calibrations_as_of", table_name="forecast_calibrations")
    op.drop_table("forecast_calibrations")
    op.drop_table("asset_forecasts")
