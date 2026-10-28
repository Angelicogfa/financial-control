"""Fundamental snapshots: when each statement was stored for the first time (Phase 25.2).

`fetched_at` changes on every refresh; `first_seen_at` tells a newly published annual statement
apart, which reopens the manual checklist answers given before it. Existing rows take their
`fetched_at`.

Revision ID: script_00022
Revises: script_00021
Create Date: 2026-10-28 12:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00022"
down_revision: str | None = "script_00021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("fundamental_snapshots") as batch:
        batch.add_column(sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE fundamental_snapshots SET first_seen_at = fetched_at")


def downgrade() -> None:
    with op.batch_alter_table("fundamental_snapshots") as batch:
        batch.drop_column("first_seen_at")
