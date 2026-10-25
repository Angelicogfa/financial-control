"""Corporate events and import hashes for B3 statement imports (items 12.3, 12.4).

Revision ID: script_00014
Revises: script_00013
Create Date: 2026-10-25 03:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00014"
down_revision: str | None = "script_00013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "corporate_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "asset_id",
            sa.Integer(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("ex_date", sa.Date(), nullable=False),
        sa.Column("factor", sa.Numeric(18, 8), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("import_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("factor > 0", name="ck_corporate_events_factor_positive"),
        sa.CheckConstraint("unit_cost >= 0", name="ck_corporate_events_unit_cost"),
        sa.UniqueConstraint("import_hash", name="uq_corporate_events_import_hash"),
    )
    op.create_index("ix_corporate_events_asset_id", "corporate_events", ["asset_id"])
    for table in ("transactions", "earnings"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("import_hash", sa.String(length=64), nullable=True))
            batch.create_unique_constraint(f"uq_{table}_import_hash", ["import_hash"])


def downgrade() -> None:
    for table in ("earnings", "transactions"):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"uq_{table}_import_hash", type_="unique")
            batch.drop_column("import_hash")
    op.drop_index("ix_corporate_events_asset_id", table_name="corporate_events")
    op.drop_table("corporate_events")
