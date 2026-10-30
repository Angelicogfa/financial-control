"""Event classes of the CVM disclosures and the measured price reactions (Phase 42.4).

`cvm_documents.event_class` keeps the class of each document ("" when it is not an event, NULL
until the worker classifies it); `cvm_event_effects` keeps, per event, the abnormal returns over
1, 5 and 20 trading days and the change in volatility, recomputed every week.

Revision ID: script_00035
Revises: script_00034
Create Date: 2026-10-30 22:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00035"
down_revision: str | None = "script_00034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("cvm_documents") as batch:
        batch.add_column(sa.Column("event_class", sa.String(length=24), nullable=True))
        batch.create_index("ix_cvm_documents_event_class", ["event_class"])
    op.create_table(
        "cvm_event_effects",
        sa.Column("document_id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_class", sa.String(length=24), nullable=False),
        sa.Column("car_1", sa.Float(), nullable=True),
        sa.Column("car_5", sa.Float(), nullable=True),
        sa.Column("car_20", sa.Float(), nullable=True),
        sa.Column("volatility_ratio", sa.Float(), nullable=True),
        sa.Column("confounded", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_cvm_event_effects_event_class", "cvm_event_effects", ["event_class"])


def downgrade() -> None:
    op.drop_index("ix_cvm_event_effects_event_class", table_name="cvm_event_effects")
    op.drop_table("cvm_event_effects")
    with op.batch_alter_table("cvm_documents") as batch:
        batch.drop_index("ix_cvm_documents_event_class")
        batch.drop_column("event_class")
