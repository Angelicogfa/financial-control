"""Investment policy: limits of the portfolio health diagnosis (Phase 29).

Versions saved before this migration keep `health` NULL and use the default limits.

Revision ID: script_00021
Revises: script_00020
Create Date: 2026-10-27 21:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00021"
down_revision: str | None = "script_00020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("investment_policies") as batch:
        batch.add_column(sa.Column("health", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("investment_policies") as batch:
        batch.drop_column("health")
