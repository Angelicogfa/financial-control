"""Asset purpose: ARCA, EMERGENCY_RESERVE or OTHER (item 10.4, finding A-03).

Existing assets stay in the ARCA allocation.

Revision ID: script_00008
Revises: script_00007
Create Date: 2026-10-25 10:30:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00008"
down_revision: str | None = "script_00007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("assets") as batch:
        batch.add_column(
            sa.Column("purpose", sa.String(length=24), nullable=False, server_default="ARCA")
        )


def downgrade() -> None:
    with op.batch_alter_table("assets") as batch:
        batch.drop_column("purpose")
