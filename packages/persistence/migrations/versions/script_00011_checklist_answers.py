"""Append-only checklist answers, evaluation history and checklist profile (item 11.4).

`assets.cerrado_answers` (a JSON map of question -> bool) becomes one MANUAL row per answer in
`checklist_answers`; the downgrade folds the latest YES/NO answers back into the JSON column.

Revision ID: script_00011
Revises: script_00010
Create Date: 2026-10-24 23:00:00
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "script_00011"
down_revision: str | None = "script_00010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MIGRATION_EVIDENCE = "Resposta registrada antes do checklist v2"


def _as_dict(raw: object) -> dict[str, object]:
    if isinstance(raw, str):
        raw = json.loads(raw or "{}")
    return dict(raw) if isinstance(raw, dict) else {}


def upgrade() -> None:
    op.create_table(
        "checklist_answers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "asset_id",
            sa.Integer(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question_id", sa.String(length=48), nullable=False),
        sa.Column("value", sa.String(length=4), nullable=True),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checklist_version", sa.Integer(), nullable=False, server_default="2"),
    )
    op.create_index(
        "ix_checklist_answers_asset_question",
        "checklist_answers",
        ["asset_id", "question_id", "answered_at"],
    )
    op.create_table(
        "checklist_evaluations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "asset_id",
            sa.Integer(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("profile", sa.String(length=16), nullable=False),
        sa.Column("checklist_version", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("normalized_score", sa.Float(), nullable=True),
        sa.Column("coverage_pct", sa.Float(), nullable=False),
        sa.Column("answered", sa.Integer(), nullable=False),
        sa.Column("applicable", sa.Integer(), nullable=False),
        sa.Column("recommendation", sa.String(length=16), nullable=False),
    )
    op.create_index(
        "ix_checklist_evaluations_asset_at", "checklist_evaluations", ["asset_id", "evaluated_at"]
    )

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, cerrado_answers, updated_at FROM assets")).all()
    now = datetime.now(UTC)
    payload = [
        {
            "asset_id": asset_id,
            "question_id": str(question_id),
            "value": "YES" if value else "NO",
            "source": "MANUAL",
            "evidence": MIGRATION_EVIDENCE,
            "answered_at": updated_at or now,
            "checklist_version": 1,
        }
        for asset_id, raw, updated_at in rows
        for question_id, value in sorted(_as_dict(raw).items())
        if value is not None
    ]
    if payload:
        # Plain SQL keeps `updated_at` as the driver returned it (text on SQLite).
        bind.execute(
            sa.text(
                "INSERT INTO checklist_answers (asset_id, question_id, value, source, evidence, "
                "answered_at, checklist_version) VALUES (:asset_id, :question_id, :value, "
                ":source, :evidence, :answered_at, :checklist_version)"
            ),
            payload,
        )

    with op.batch_alter_table("assets") as batch:
        batch.drop_column("cerrado_answers")
        batch.add_column(sa.Column("checklist_profile", sa.String(length=16), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("assets") as batch:
        batch.add_column(
            sa.Column("cerrado_answers", sa.JSON(), nullable=False, server_default="{}")
        )
        batch.drop_column("checklist_profile")

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT asset_id, question_id, value FROM checklist_answers "
            "ORDER BY asset_id, answered_at, id"
        )
    ).all()
    latest: dict[int, dict[str, object]] = {}
    for asset_id, question_id, value in rows:
        latest.setdefault(asset_id, {})[question_id] = value
    # Postgres needs an explicit cast from text; SQLite stores JSON as text already.
    value = "CAST(:answers AS JSON)" if bind.dialect.name == "postgresql" else ":answers"
    for asset_id, answers in latest.items():
        legacy = {q: v == "YES" for q, v in answers.items() if v in ("YES", "NO")}
        bind.execute(
            sa.text(f"UPDATE assets SET cerrado_answers = {value} WHERE id = :id"),
            {"answers": json.dumps(legacy), "id": asset_id},
        )

    op.drop_index("ix_checklist_evaluations_asset_at", table_name="checklist_evaluations")
    op.drop_table("checklist_evaluations")
    op.drop_index("ix_checklist_answers_asset_question", table_name="checklist_answers")
    op.drop_table("checklist_answers")
