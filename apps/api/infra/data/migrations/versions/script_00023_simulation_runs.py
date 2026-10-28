"""Portfolio simulation runs and their results (Phase 33.3).

A run stores its parameters, the hash of the data it read, the engine version and the seed,
so the same inputs always give the same results and a finished run can be reused.

Revision ID: script_00023
Revises: script_00022
Create Date: 2026-10-28 18:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00023"
down_revision: str | None = "script_00022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "simulation_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("label", sa.String(120), nullable=True),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("params_hash", sa.String(64), nullable=False),
        sa.Column("data_hash", sa.String(64), nullable=True),
        sa.Column("code_version", sa.String(32), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("reused_from", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_simulation_runs_status", "simulation_runs", ["status"])
    op.create_index("ix_simulation_runs_params_hash", "simulation_runs", ["params_hash"])
    op.create_table(
        "simulation_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("simulation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(40), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("points", sa.JSON(), nullable=False),
        sa.Column("extra", sa.JSON(), nullable=False),
    )
    op.create_index("ix_simulation_results_run_id", "simulation_results", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_simulation_results_run_id", table_name="simulation_results")
    op.drop_table("simulation_results")
    op.drop_index("ix_simulation_runs_params_hash", table_name="simulation_runs")
    op.drop_index("ix_simulation_runs_status", table_name="simulation_runs")
    op.drop_table("simulation_runs")
