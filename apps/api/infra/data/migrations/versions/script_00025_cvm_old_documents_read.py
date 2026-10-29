"""Mark as read the CVM documents that were already old when first loaded.

The first CVM load brought two years of filings, all unread (thousands of "new" documents).
From now on a document delivered more than 30 days before it is first seen arrives read; this
applies the same rule to the rows loaded before it: delivered more than 30 days before the
first load.

Revision ID: script_00025
Revises: script_00024
Create Date: 2026-10-29 13:00:00
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

import sqlalchemy as sa
from alembic import op

revision: str = "script_00025"
down_revision: str | None = "script_00024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STALE_DAYS = 30


def upgrade() -> None:
    bind = op.get_bind()
    documents = sa.table(
        "cvm_documents",
        sa.column("read_at", sa.DateTime(timezone=True)),
        sa.column("first_seen_at", sa.DateTime(timezone=True)),
        sa.column("delivery_date", sa.Date()),
    )
    first_load = bind.execute(sa.select(sa.func.min(documents.c.first_seen_at))).scalar()
    if first_load is None:
        return
    if isinstance(first_load, str):  # SQLite returns the text it stored
        first_load = datetime.fromisoformat(first_load[:19])
    cutoff = first_load.date() - timedelta(days=STALE_DAYS)
    bind.execute(
        documents.update()
        .where(documents.c.read_at.is_(None), documents.c.delivery_date < cutoff)
        .values(read_at=first_load)
    )


def downgrade() -> None:
    # The read marks cannot be told apart from the ones the user set; nothing to undo.
    pass
