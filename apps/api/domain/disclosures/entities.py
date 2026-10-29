"""Disclosures filed with the CVM (IPE) and the ticker -> CNPJ map (FCA), Phase 28.

The IPE dataset (`ipe_cia_aberta_AAAA.zip`) lists every periodic and eventual document of a
listed company: relevant facts, market notices, shareholder notices, meetings. The FCA
(`fca_cia_aberta_valor_mobiliario_AAAA.csv`) gives the trading codes of each CNPJ, which is how
a ticker of the portfolio finds its company. FIIs are not companies: they are not in the IPE.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

# The categories that matter most, in the CVM's own words.
RELEVANT_FACT = "Fato Relevante"
MARKET_NOTICE = "Comunicado ao Mercado"
SHAREHOLDER_NOTICE = "Aviso aos Acionistas"
MAIN_CATEGORIES: tuple[str, ...] = (RELEVANT_FACT, MARKET_NOTICE, SHAREHOLDER_NOTICE)


def normalize_cnpj(raw: str) -> str:
    """Digits only (the CVM writes 84.429.695/0001-11)."""
    return "".join(ch for ch in raw if ch.isdigit())


@dataclass(frozen=True)
class IssuerTicker:
    """A trading code of a company, from the FCA."""

    ticker: str
    cnpj: str  # digits only
    company_name: str
    reference_date: date | None = None


@dataclass(frozen=True)
class CvmDocument:
    """One IPE document. The protocol identifies it; a new version replaces the old one."""

    protocol: str
    cnpj: str  # digits only
    company_name: str
    category: str
    delivery_date: date
    cvm_code: str = ""
    doc_type: str = ""
    species: str = ""
    subject: str = ""
    reference_date: date | None = None
    version: int = 1
    link: str = ""
    first_seen_at: datetime | None = None
    read_at: datetime | None = None
    id: int | None = None

    @property
    def is_relevant_fact(self) -> bool:
        return self.category == RELEVANT_FACT
