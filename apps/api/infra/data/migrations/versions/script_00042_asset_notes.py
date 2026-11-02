"""Thesis notes of each asset, with the date to review them (Phase 48.R6).

Additive only: a new table that points at `assets` (removed with the asset).

Revision ID: script_00042
Revises: script_00041
Create Date: 2026-11-02 18:05:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00042"
down_revision: str | None = "script_00041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "asset_notes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "asset_id",
            sa.Integer(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("written_on", sa.Date(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("review_at", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_asset_notes_asset_id", "asset_notes", ["asset_id"])


def downgrade() -> None:
    op.drop_index("ix_asset_notes_asset_id", table_name="asset_notes")
    op.drop_table("asset_notes")
