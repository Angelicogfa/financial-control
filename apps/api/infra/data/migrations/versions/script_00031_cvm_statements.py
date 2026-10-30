"""Statements delivered to the CVM (DFP/ITR), point in time (Phase 42.2).

`cvm_statements` keeps the metrics of each delivered statement and version with its delivery
date, so a past date sees only what had been delivered; `cvm_statement_loads` records which
yearly file was loaded and from which version of the file.

Revision ID: script_00031
Revises: script_00030
Create Date: 2026-10-30 10:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00031"
down_revision: str | None = "script_00030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cvm_statements",
        sa.Column("cnpj", sa.String(length=14), primary_key=True),
        sa.Column("doc_type", sa.String(length=3), primary_key=True),
        sa.Column("reference_date", sa.Date(), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("metric", sa.String(length=32), primary_key=True),
        sa.Column("delivered_on", sa.Date(), nullable=False),
        sa.Column("basis", sa.String(length=3), nullable=False),
        sa.Column("template", sa.String(length=10), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
    )
    op.create_index("ix_cvm_statements_cnpj_delivered", "cvm_statements", ["cnpj", "delivered_on"])
    op.create_index("ix_cvm_statements_doc", "cvm_statements", ["doc_type", "reference_date"])
    op.create_table(
        "cvm_statement_loads",
        sa.Column("doc_type", sa.String(length=3), primary_key=True),
        sa.Column("year", sa.Integer(), primary_key=True),
        sa.Column("source_stamp", sa.String(length=64), nullable=False),
        sa.Column("facts", sa.Integer(), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("cvm_statement_loads")
    op.drop_index("ix_cvm_statements_doc", table_name="cvm_statements")
    op.drop_index("ix_cvm_statements_cnpj_delivered", table_name="cvm_statements")
    op.drop_table("cvm_statements")
