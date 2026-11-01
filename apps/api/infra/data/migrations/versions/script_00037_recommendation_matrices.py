"""AHP premises in the policy and the decision matrices of the recommendation (Phase 45.3).

`investment_policies.recommendation` keeps, per policy version, the objective of each ARCA class,
the AHP pairwise matrix of the lenses per objective and the scale of the expected return (NULL
on earlier versions: they take the pre-configured defaults). `recommendation_matrices` keeps, per
weekly run and class, the decision matrix: weights, consistency ratio, the ranked eligible assets
lens by lens, the Gaussian AHP reference and the assets left out by the gates; and, from 45.4,
the construction of the weights (selected assets, dynamic-K curve and who was left out).
`recommendation_runs` is the history (45.5): per run, the policy version applied, the month of the
signals, the counts and the assets chosen in each class.

Revision ID: script_00037
Revises: script_00036
Create Date: 2026-10-31 14:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "script_00037"
down_revision: str | None = "script_00036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("investment_policies", sa.Column("recommendation", sa.JSON(), nullable=True))
    op.create_table(
        "recommendation_matrices",
        sa.Column("as_of", sa.Date(), primary_key=True),
        sa.Column("arca_class", sa.String(length=32), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("construction", sa.JSON(), nullable=True),
    )
    op.create_table(
        "recommendation_runs",
        sa.Column("as_of", sa.Date(), primary_key=True),
        sa.Column("policy_version", sa.Integer(), nullable=True),
        sa.Column("signal_month", sa.Date(), nullable=True),
        sa.Column("assets", sa.Integer(), nullable=False),
        sa.Column("eligible", sa.Integer(), nullable=False),
        sa.Column("selected", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("recommendation_runs")
    op.drop_table("recommendation_matrices")
    op.drop_column("investment_policies", "recommendation")
