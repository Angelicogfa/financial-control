"""Store the FX rate of each earning payment (finding C-02).

Existing rows default to 1.0; foreign-currency earnings recorded before this revision are
re-priced with the historical USD/BRL rate by `python -m fincontrol_worker.rebuild`.

Revision ID: script_00004
Revises: script_00003
Create Date: 2026-10-24 18:20:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00004"
down_revision: str | None = "script_00003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("earnings") as batch:
        batch.add_column(
            sa.Column("fx_rate", sa.Numeric(14, 6), nullable=False, server_default="1")
        )
        batch.create_check_constraint("ck_earnings_fx_rate_positive", "fx_rate > 0")


def downgrade() -> None:
    with op.batch_alter_table("earnings") as batch:
        batch.drop_constraint("ck_earnings_fx_rate_positive", type_="check")
        batch.drop_column("fx_rate")
