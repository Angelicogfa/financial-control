"""Tax rule registry: IR and IOF rates with validity periods, seeded with the 2026 rules.

A legal change is a new migration that ends the current record (`valid_to`) and inserts the
new one, so past events keep the rate that was in force on their date. The seed mirrors
`domain.tax.services.rules.DEFAULT_TAX_RULES` (inlined so the migration never changes when
the domain module evolves).

Revision ID: script_00019
Revises: script_00018
Create Date: 2026-10-27 10:00:00
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa
from alembic import op

revision: str = "script_00019"
down_revision: str | None = "script_00018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IOF_TABLE = (
    0.96, 0.93, 0.90, 0.86, 0.83, 0.80, 0.76, 0.73, 0.70, 0.66,
    0.63, 0.60, 0.56, 0.53, 0.50, 0.46, 0.43, 0.40, 0.36, 0.33,
    0.30, 0.26, 0.23, 0.20, 0.16, 0.13, 0.10, 0.06, 0.03,
)  # fmt: skip


def _flat(rate: float) -> list[dict[str, float | None]]:
    return [{"up_to_days": None, "rate": rate}]


REGRESSIVE = [
    {"up_to_days": 180, "rate": 0.225},
    {"up_to_days": 360, "rate": 0.200},
    {"up_to_days": 720, "rate": 0.175},
    {"up_to_days": None, "rate": 0.150},
]
IOF = [
    {"up_to_days": 0, "rate": 0.0},
    *({"up_to_days": day, "rate": rate} for day, rate in enumerate(IOF_TABLE, start=1)),
    {"up_to_days": None, "rate": 0.0},
]

SEED = [
    (
        "FIXED_INCOME_REGRESSIVE", "INCOME_TAX", REGRESSIVE, date(2005, 1, 1), None,
        "Lei 11.033/2004, art. 1º",
        "Renda fixa tributada: IR regressivo sobre o rendimento, retido no resgate.",
    ),
    (
        "FIXED_INCOME_EXEMPT", "INCOME_TAX", _flat(0.0), date(2005, 1, 1), None,
        "Lei 11.033/2004, art. 3º; Lei 12.431/2011",
        "LCI, LCA, CRI, CRA e debêntures incentivadas: rendimento isento para PF.",
    ),
    (
        "IOF_REGRESSIVE", "IOF", IOF, date(2008, 1, 1), None,
        "Decreto 6.306/2007, art. 32",
        "IOF regressivo sobre o rendimento de resgates com menos de 30 dias.",
    ),
    (
        "STOCK_SWING_TRADE", "INCOME_TAX", _flat(0.15), date(2005, 1, 1), None,
        "Lei 11.033/2004, art. 2º; Lei 11.196/2005, art. 38",
        "Ações: 15% sobre o lucro de operações comuns, apurado mensalmente (DARF); "
        "isento quando as vendas do mês somam até R$ 20 mil. Day trade: 20%.",
    ),
    (
        "ETF_BDR_SWING_TRADE", "INCOME_TAX", _flat(0.15), date(2005, 1, 1), None,
        "Lei 11.033/2004, art. 2º; IN RFB 1.585/2015",
        "ETFs de renda variável e BDRs: 15% sobre o lucro, apurado mensalmente, sem a "
        "isenção de R$ 20 mil. Day trade: 20%.",
    ),
    (
        "FII_CAPITAL_GAIN", "INCOME_TAX", _flat(0.20), date(2005, 1, 1), None,
        "Lei 8.668/1993, art. 18; Lei 11.033/2004",
        "FIIs e Fiagros: 20% sobre o lucro na venda das cotas, sem isenção.",
    ),
    (
        "FII_DISTRIBUTION", "INCOME_TAX", _flat(0.0), date(2005, 1, 1), None,
        "Lei 11.033/2004, art. 3º, III",
        "Rendimentos de FII isentos para PF (fundo com 100+ cotistas, cotas em bolsa e "
        "participação abaixo de 10%).",
    ),
    (
        "DIVIDEND_WITHHOLDING", "INCOME_TAX", _flat(0.0), date(1996, 1, 1), date(2025, 12, 31),
        "Lei 9.249/1995, art. 10",
        "Dividendos isentos para PF.",
    ),
    (
        "DIVIDEND_WITHHOLDING", "INCOME_TAX", _flat(0.10), date(2026, 1, 1), None,
        "Lei 15.270/2025",
        "Dividendos: 10% retidos sobre o que exceder R$ 50 mil por mês da mesma empresa "
        "para a mesma PF; abaixo disso seguem isentos.",
    ),
    (
        "JCP_WITHHOLDING", "INCOME_TAX", _flat(0.15), date(1996, 1, 1), date(2025, 12, 31),
        "Lei 9.249/1995, art. 9º, § 2º",
        "Juros sobre capital próprio: 15% retidos na fonte.",
    ),
    (
        "JCP_WITHHOLDING", "INCOME_TAX", _flat(0.175), date(2026, 1, 1), None,
        "LC 224/2025",
        "Juros sobre capital próprio: 17,5% retidos na fonte a partir de 2026.",
    ),
    (
        "FOREIGN_ANNUAL", "INCOME_TAX", _flat(0.15), date(2024, 1, 1), None,
        "Lei 14.754/2023",
        "Aplicações no exterior: 15% sobre ganhos e rendimentos, apurados anualmente na "
        "declaração de ajuste.",
    ),
    (
        "CRYPTO_CAPITAL_GAIN", "INCOME_TAX", _flat(0.15), date(2005, 1, 1), None,
        "Lei 8.981/1995, art. 21; Lei 13.259/2016",
        "Criptoativos: ganho de capital a partir de 15% (progressivo até 22,5% pelo "
        "valor do ganho); isento quando as vendas do mês somam até R$ 35 mil.",
    ),
]  # fmt: skip


def upgrade() -> None:
    table = op.create_table(
        "tax_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("regime", sa.String(length=40), nullable=False),
        sa.Column("tax_kind", sa.String(length=16), nullable=False),
        sa.Column("brackets", sa.JSON(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("legal_basis", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("description", sa.String(length=400), nullable=False, server_default=""),
    )
    op.create_index("ix_tax_rules_regime", "tax_rules", ["regime"])
    op.bulk_insert(
        table,
        [
            {
                "regime": regime,
                "tax_kind": kind,
                "brackets": brackets,
                "valid_from": valid_from,
                "valid_to": valid_to,
                "legal_basis": basis,
                "description": description,
            }
            for regime, kind, brackets, valid_from, valid_to, basis, description in SEED
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_tax_rules_regime", table_name="tax_rules")
    op.drop_table("tax_rules")
