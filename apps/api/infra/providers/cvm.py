"""CVM open data: company disclosures (IPE) and trading codes (FCA), Phase 28.

Both come from https://dados.cvm.gov.br as one ZIP per year with `;`-separated CSVs in
latin-1, free and keyless:
- `CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_AAAA.zip`: every eventual document (relevant
  facts, market notices, shareholder notices, meetings) with the delivery date and the link;
- `CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_AAAA.zip`, file `..._valor_mobiliario_AAAA.csv`:
  the trading code (`Codigo_Negociacao`) of each CNPJ.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Iterable
from datetime import date

import httpx

from domain.disclosures.entities import CvmDocument, IssuerTicker, normalize_cnpj
from infra.providers.error_tracker import report_provider_error

DEFAULT_CVM_BASE_URL = "https://dados.cvm.gov.br/dados"
IPE_PATH = "/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{year}.zip"
FCA_PATH = "/CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_{year}.zip"
ENCODING = "latin-1"


def _date(raw: str | None) -> date | None:
    text = (raw or "").strip()
    try:
        return date.fromisoformat(text[:10]) if text else None
    except ValueError:
        return None


def _rows(text: str) -> Iterable[dict[str, str]]:
    return csv.DictReader(io.StringIO(text), delimiter=";")


def _member(content: bytes, contains: str) -> str | None:
    """Text of the first CSV in the ZIP whose name contains `contains`."""
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for name in archive.namelist():
            if contains in name and name.endswith(".csv"):
                return archive.read(name).decode(ENCODING)
    return None


def parse_ipe(text: str) -> list[CvmDocument]:
    """IPE rows as documents; rows without a protocol, CNPJ or delivery date are skipped."""
    out: list[CvmDocument] = []
    for row in _rows(text):
        protocol = (row.get("Protocolo_Entrega") or "").strip()
        cnpj = normalize_cnpj(row.get("CNPJ_Companhia") or "")
        delivered = _date(row.get("Data_Entrega"))
        if not protocol or not cnpj or delivered is None:
            continue
        try:
            version = int((row.get("Versao") or "1").strip() or 1)
        except ValueError:
            version = 1
        out.append(
            CvmDocument(
                protocol=protocol,
                cnpj=cnpj,
                company_name=(row.get("Nome_Companhia") or "").strip(),
                cvm_code=(row.get("Codigo_CVM") or "").strip(),
                category=(row.get("Categoria") or "").strip(),
                doc_type=(row.get("Tipo") or "").strip(),
                species=(row.get("Especie") or "").strip(),
                subject=(row.get("Assunto") or "").strip(),
                reference_date=_date(row.get("Data_Referencia")),
                delivery_date=delivered,
                version=version,
                link=(row.get("Link_Download") or "").strip(),
            )
        )
    return out


def parse_fca_tickers(text: str) -> list[IssuerTicker]:
    """Trading codes of each CNPJ; the newest reference date wins for a repeated ticker."""
    best: dict[str, IssuerTicker] = {}
    for row in _rows(text):
        ticker = (row.get("Codigo_Negociacao") or "").strip().upper()
        cnpj = normalize_cnpj(row.get("CNPJ_Companhia") or "")
        if not ticker or not cnpj:
            continue
        item = IssuerTicker(
            ticker=ticker,
            cnpj=cnpj,
            company_name=(row.get("Nome_Empresarial") or "").strip(),
            reference_date=_date(row.get("Data_Referencia")),
        )
        current = best.get(ticker)
        if current is None or (item.reference_date or date.min) >= (
            current.reference_date or date.min
        ):
            best[ticker] = item
    return list(best.values())


class CvmOpenDataProvider:
    """HTTP client of the CVM open data portal."""

    PROVIDER_NAME = "cvm"

    def __init__(
        self,
        base_url: str = DEFAULT_CVM_BASE_URL,
        client: httpx.Client | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=True)

    def _download(self, url: str, operation: str, target: str) -> bytes | None:
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
            return resp.content
        except Exception as exc:
            report_provider_error(
                provider=self.PROVIDER_NAME,
                operation=operation,
                target=target,
                request_url=url,
                exc=exc,
            )
            return None

    def _csv(self, url: str, operation: str, year: int, member: str) -> str | None:
        content = self._download(url, operation, str(year))
        if content is None:
            return None
        try:
            return _member(content, member)
        except zipfile.BadZipFile as exc:  # an error page instead of the archive
            report_provider_error(
                provider=self.PROVIDER_NAME,
                operation=operation,
                target=str(year),
                request_url=url,
                exc=exc,
            )
            return None

    def documents(self, year: int) -> list[CvmDocument]:
        """Every IPE document delivered in `year` (empty when the file is unavailable)."""
        url = f"{self.base_url}{IPE_PATH.format(year=year)}"
        text = self._csv(url, "ipe", year, "ipe_cia_aberta")
        return parse_ipe(text) if text else []

    def issuer_tickers(self, year: int) -> list[IssuerTicker]:
        """Trading codes declared in the FCA of `year`."""
        url = f"{self.base_url}{FCA_PATH.format(year=year)}"
        text = self._csv(url, "fca", year, "valor_mobiliario")
        return parse_fca_tickers(text) if text else []
