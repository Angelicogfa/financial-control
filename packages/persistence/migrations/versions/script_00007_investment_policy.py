"""Versioned investment policy replaces arca_targets (item 10.1, ADR 0005).

The current ARCA targets and strategies become policy version 1 with a 5 p.p. tolerance
band per class and default eligibility/valuation rules. Downgrade rebuilds arca_targets
from the latest policy version.

Revision ID: script_00007
Revises: script_00006
Create Date: 2026-10-25 10:00:00
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "script_00007"
down_revision: str | None = "script_00006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ARCA_CLASSES = ("ACOES", "REAL_ESTATE", "CAIXA", "ATIVOS_INTERNACIONAIS")
DEFAULT_BAND_PCT = 5.0
DEFAULT_ELIGIBILITY = {"require_evaluation": False, "min_score": 1, "min_coverage_pct": 0.0}
DEFAULT_VALUATION = {
    "bazin_required_yield": 0.06,
    "graham_multiplier": 22.5,
    "projections": {
        "equity_capital_growth_rate": 0.08,
        "fund_capital_growth_rate": 0.10,
        "real_estate_default_yield_rate": 0.085,
        "cash_cdi_multiplier": 1.0,
        "cash_income_tax_rate": 0.175,
    },
}


def upgrade() -> None:
    policies = op.create_table(
        "investment_policies",
        sa.Column("version", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("arca", sa.JSON(), nullable=False),
        sa.Column("eligibility", sa.JSON(), nullable=False),
        sa.Column("valuation", sa.JSON(), nullable=False),
    )

    rows = op.get_bind().execute(
        sa.text("SELECT arca_class, target_pct, intra_class_strategy FROM arca_targets")
    ).all()
    arca = {
        cls: {"target_pct": 25.0, "band_pct": DEFAULT_BAND_PCT, "intra_class_strategy": "CERRADO"}
        for cls in ARCA_CLASSES
    }
    for arca_class, target_pct, strategy in rows:
        arca[arca_class] = {
            "target_pct": float(target_pct),
            "band_pct": DEFAULT_BAND_PCT,
            "intra_class_strategy": strategy,
        }
    op.bulk_insert(
        policies,
        [
            {
                "created_at": datetime.now(UTC),
                "arca": arca,
                "eligibility": DEFAULT_ELIGIBILITY,
                "valuation": DEFAULT_VALUATION,
            }
        ],
    )
    op.drop_table("arca_targets")


def downgrade() -> None:
    targets = op.create_table(
        "arca_targets",
        sa.Column("arca_class", sa.String(length=32), primary_key=True),
        sa.Column("target_pct", sa.Numeric(6, 2), nullable=False),
        sa.Column("intra_class_strategy", sa.String(length=24), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "target_pct >= 0 AND target_pct <= 100", name="ck_arca_targets_pct_bounds"
        ),
    )
    latest = op.get_bind().execute(
        sa.text("SELECT arca FROM investment_policies ORDER BY version DESC LIMIT 1")
    ).scalar()
    arca = json.loads(latest) if isinstance(latest, str) else (latest or {})
    now = datetime.now(UTC)
    op.bulk_insert(
        targets,
        [
            {
                "arca_class": cls,
                "target_pct": arca.get(cls, {}).get("target_pct", 25.0),
                "intra_class_strategy": arca.get(cls, {}).get("intra_class_strategy", "CERRADO"),
                "updated_at": now,
            }
            for cls in ARCA_CLASSES
        ],
    )
    op.drop_table("investment_policies")
