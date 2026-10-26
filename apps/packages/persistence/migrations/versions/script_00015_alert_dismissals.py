"""Alerts hidden by the user (item 12.2).

Revision ID: script_00015
Revises: script_00014
Create Date: 2026-10-25 04:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00015"
down_revision: str | None = "script_00014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alert_dismissals",
        sa.Column("key", sa.String(length=160), primary_key=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("until", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("alert_dismissals")
