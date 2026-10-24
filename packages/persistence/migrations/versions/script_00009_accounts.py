"""Custody accounts; every trade and earning belongs to one (item 10.5, finding D-01).

Existing rows are assigned to a default account named "Principal".

Revision ID: script_00009
Revises: script_00008
Create Date: 2026-10-25 11:00:00
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "script_00009"
down_revision: str | None = "script_00008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEDGER_TABLES = ("transactions", "earnings")


def upgrade() -> None:
    accounts = op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("institution", sa.String(length=120), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="BROKER"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_accounts_name"),
    )
    op.bulk_insert(
        accounts,
        [
            {
                "id": 1,
                "name": "Principal",
                "institution": None,
                "kind": "BROKER",
                "is_active": True,
                "created_at": datetime.now(UTC),
            }
        ],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("SELECT setval(pg_get_serial_sequence('accounts', 'id'), 1)")

    for table in LEDGER_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("account_id", sa.Integer(), nullable=True))
        op.execute(f"UPDATE {table} SET account_id = 1")
        with op.batch_alter_table(table) as batch:
            batch.alter_column("account_id", existing_type=sa.Integer(), nullable=False)
            batch.create_foreign_key(f"fk_{table}_account", "accounts", ["account_id"], ["id"])
            batch.create_index(f"ix_{table}_account_id", ["account_id"])


def downgrade() -> None:
    for table in LEDGER_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.drop_index(f"ix_{table}_account_id")
            batch.drop_constraint(f"fk_{table}_account", type_="foreignkey")
            batch.drop_column("account_id")
    op.drop_table("accounts")
