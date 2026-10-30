"""Simulation studies (Phase 41): a question, premises set once, chapters that answer it.

Creates `simulation_studies`, links each run to its study chapter (`study_id`, `chapter`) and
turns every existing backtest, projection and candidates run into a one-chapter study, so the
new screen keeps every result already computed.

Revision ID: script_00029
Revises: script_00028
Create Date: 2026-10-30 09:00:00
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "script_00029"
down_revision: str | None = "script_00028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Run kind -> (study question, chapter, default name).
CONVERSION = {
    "BACKTEST": ("PAST", "PAST", "Minhas regras teriam funcionado?"),
    "PROJECTION": ("GOAL", "FUTURE", "Vou chegar à minha meta?"),
    "CANDIDATES": ("IMPROVE", "IMPROVE", "O que acrescentar à carteira?"),
}


def _premises(kind: str, params: dict[str, Any]) -> dict[str, Any]:
    source = params.get("projection", params) if kind == "CANDIDATES" else params
    premises: dict[str, Any] = {
        "monthly_contribution": float(source.get("monthly_contribution") or 0.0),
    }
    if kind == "BACKTEST":
        premises.update(
            past_start=params.get("start"),
            correct_by_ipca=bool(params.get("correct_by_ipca", False)),
            policy_mode=params.get("policy_mode", "CURRENT"),
            answers_mode=params.get("answers_mode", "DATED"),
            benchmarks=params.get("benchmarks", ["CDI", "IBOV"]),
            rebalance=bool(params.get("rebalance", False)),
        )
    else:
        if source.get("horizon_months"):
            premises["horizon_years"] = max(1, int(source["horizon_months"]) // 12)
        elif source.get("horizon_years"):
            premises["horizon_years"] = int(source["horizon_years"])
        if source.get("wealth_goal"):
            premises["wealth_goal"] = float(source["wealth_goal"])
    return {k: v for k, v in premises.items() if v is not None}


def upgrade() -> None:
    op.create_table(
        "simulation_studies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("question", sa.String(length=16), nullable=False),
        sa.Column("premises", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("origin_id", sa.Integer(), nullable=True),
        sa.Column("variation_of", sa.Integer(), nullable=True),
        sa.Column("notes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_simulation_studies_origin_id", "simulation_studies", ["origin_id"])
    op.create_index("ix_simulation_studies_deleted_at", "simulation_studies", ["deleted_at"])
    with op.batch_alter_table("simulation_runs") as batch:
        batch.add_column(sa.Column("study_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("chapter", sa.String(length=16), nullable=True))
    op.create_index("ix_simulation_runs_study_id", "simulation_runs", ["study_id"])

    bind = op.get_bind()
    studies = sa.table(
        "simulation_studies",
        sa.column("id", sa.Integer()),
        sa.column("label", sa.String()),
        sa.column("question", sa.String()),
        sa.column("premises", sa.JSON()),
        sa.column("version", sa.Integer()),
        sa.column("notes", sa.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    runs = bind.execute(
        sa.text(
            "SELECT id, kind, label, params, created_at FROM simulation_runs "
            "WHERE deleted_at IS NULL AND kind IN ('BACKTEST', 'PROJECTION', 'CANDIDATES') "
            "ORDER BY id"
        )
    ).fetchall()
    for run_id, kind, label, params, created_at in runs:
        question, chapter, default = CONVERSION[kind]
        data = json.loads(params) if isinstance(params, str) else (params or {})
        if isinstance(created_at, str):  # SQLite hands back text
            created_at = datetime.fromisoformat(created_at[:19])
        result = bind.execute(
            studies.insert()
            .values(
                label=(label or default)[:120],
                question=question,
                premises=_premises(kind, data),
                version=1,
                notes=[],
                created_at=created_at or datetime.now(UTC),
            )
            .returning(studies.c.id)
        )
        study_id = result.scalar_one()
        bind.execute(
            sa.text("UPDATE simulation_runs SET study_id = :s, chapter = :c WHERE id = :r"),
            {"s": study_id, "c": chapter, "r": run_id},
        )


def downgrade() -> None:
    op.drop_index("ix_simulation_runs_study_id", table_name="simulation_runs")
    with op.batch_alter_table("simulation_runs") as batch:
        batch.drop_column("chapter")
        batch.drop_column("study_id")
    op.drop_index("ix_simulation_studies_deleted_at", table_name="simulation_studies")
    op.drop_index("ix_simulation_studies_origin_id", table_name="simulation_studies")
    op.drop_table("simulation_studies")
