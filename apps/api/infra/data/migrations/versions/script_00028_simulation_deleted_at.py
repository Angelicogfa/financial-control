"""Logical deletion of simulation runs (Phase 40.4).

A deleted run is hidden from every listing, lookup and reuse and cannot be restored; its rows
stay in the database for the audit trail.

Revision ID: script_00028
Revises: script_00027
Create Date: 2026-10-29 21:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00028"
down_revision: str | None = "script_00027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("simulation_runs") as batch:
        batch.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_simulation_runs_deleted_at", "simulation_runs", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_simulation_runs_deleted_at", table_name="simulation_runs")
    with op.batch_alter_table("simulation_runs") as batch:
        batch.drop_column("deleted_at")
