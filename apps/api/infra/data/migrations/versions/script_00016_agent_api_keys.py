"""Personal MCP agent API keys with scoped tool grants.

Revision ID: script_00016
Revises: script_00015
Create Date: 2026-10-26 20:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00016"
down_revision: str | None = "script_00015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_api_keys",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("prefix", sa.String(length=16), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("grant_scope", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("key_hash", name="uq_agent_api_keys_key_hash"),
    )
    op.create_index("ix_agent_api_keys_key_hash", "agent_api_keys", ["key_hash"])
    op.create_index("ix_agent_api_keys_user_id", "agent_api_keys", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_api_keys_user_id", table_name="agent_api_keys")
    op.drop_index("ix_agent_api_keys_key_hash", table_name="agent_api_keys")
    op.drop_table("agent_api_keys")
