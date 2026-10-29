"""CVM disclosures (Phase 28): IPE documents and the FCA ticker -> CNPJ map.

`cvm_documents` keeps one row per protocol (a new version replaces the old one) with when it
was first seen here and when it was read; `cvm_issuer_tickers` maps each trading code to the
company CNPJ, so the documents of the held and followed companies can be found.

Revision ID: script_00024
Revises: script_00023
Create Date: 2026-10-29 09:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00024"
down_revision: str | None = "script_00023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cvm_issuer_tickers",
        sa.Column("ticker", sa.String(16), primary_key=True),
        sa.Column("cnpj", sa.String(14), nullable=False),
        sa.Column("company_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("reference_date", sa.Date(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_cvm_issuer_tickers_cnpj", "cvm_issuer_tickers", ["cnpj"])
    op.create_table(
        "cvm_documents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("protocol", sa.String(64), nullable=False, unique=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cnpj", sa.String(14), nullable=False),
        sa.Column("company_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("cvm_code", sa.String(16), nullable=False, server_default=""),
        sa.Column("category", sa.String(120), nullable=False),
        sa.Column("doc_type", sa.String(120), nullable=False, server_default=""),
        sa.Column("species", sa.String(120), nullable=False, server_default=""),
        sa.Column("subject", sa.Text(), nullable=False, server_default=""),
        sa.Column("reference_date", sa.Date(), nullable=True),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("link", sa.Text(), nullable=False, server_default=""),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_cvm_documents_cnpj", "cvm_documents", ["cnpj"])
    op.create_index("ix_cvm_documents_category", "cvm_documents", ["category"])
    op.create_index("ix_cvm_documents_delivery_date", "cvm_documents", ["delivery_date"])


def downgrade() -> None:
    op.drop_index("ix_cvm_documents_delivery_date", table_name="cvm_documents")
    op.drop_index("ix_cvm_documents_category", table_name="cvm_documents")
    op.drop_index("ix_cvm_documents_cnpj", table_name="cvm_documents")
    op.drop_table("cvm_documents")
    op.drop_index("ix_cvm_issuer_tickers_cnpj", table_name="cvm_issuer_tickers")
    op.drop_table("cvm_issuer_tickers")
