"""Normalize fixed income contracted rates to the ADR 0006 scale (finding I-02).

Before this revision the engine guessed the scale: CDI/SELIC rates above 5 were read as
percentages (110 -> 1.10) and PRE/IPCA rates above 1 as percentages (6.5 -> 0.065). The
same rule is applied once here so stored values keep their original meaning, and from now
on the domain rejects values outside the canonical ranges.

Revision ID: script_00003
Revises: script_00002
Create Date: 2026-10-24 18:10:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "script_00003"
down_revision: str | None = "script_00002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE fixed_income_terms
        SET contracted_rate = contracted_rate / 100.0
        WHERE (indexer IN ('CDI', 'SELIC') AND contracted_rate > 5)
           OR (indexer IN ('PRE', 'IPCA') AND contracted_rate > 1)
        """
    )


def downgrade() -> None:
    # Canonical values remain valid under the previous heuristic, so nothing to undo.
    pass
