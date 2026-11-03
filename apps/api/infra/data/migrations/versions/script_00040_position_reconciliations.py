"""Position check against the B3 Posição statement (Phase 48.R5).

`position_reconciliations` keeps each check (reference date, file and its hash);
`position_reconciliation_lines` keeps each ticker and account with the statement and the
ledger quantities, the status and the investor's resolution. Additive only: no existing
table changes.

Revision ID: script_00040
Revises: script_00039
Create Date: 2026-11-02 12:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00040"
down_revision: str | None = "script_00039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "position_reconciliations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("reference_date", sa.Date(), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("reference_date", "file_hash", name="uq_position_reconciliations_file"),
    )
    op.create_index(
        "ix_position_reconciliations_reference_date",
        "position_reconciliations",
        ["reference_date"],
    )
    op.create_table(
        "position_reconciliation_lines",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "reconciliation_id",
            sa.Integer(),
            sa.ForeignKey("position_reconciliations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product", sa.String(64), nullable=False),
        sa.Column("ticker", sa.String(32), nullable=True),
        sa.Column("asset_id", sa.Integer(), nullable=True),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("institution", sa.String(255), nullable=True),
        sa.Column("b3_quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("ledger_quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("resolution", sa.String(16), nullable=False, server_default="OPEN"),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_position_reconciliation_lines_reconciliation_id",
        "position_reconciliation_lines",
        ["reconciliation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_position_reconciliation_lines_reconciliation_id",
        table_name="position_reconciliation_lines",
    )
    op.drop_table("position_reconciliation_lines")
    op.drop_index(
        "ix_position_reconciliations_reference_date", table_name="position_reconciliations"
    )
    op.drop_table("position_reconciliations")
