"""CVM open data: disclosures (IPE) and trading codes (FCA), Phase 28; statements (DFP/ITR), 42.2.

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
from domain.disclosures.statements import (
    CONSOLIDATED,
    INDIVIDUAL,
    SCALES,
    AccountRow,
    StatementDoc,
    StatementFact,
    extract_facts,
    needed,
)
from infra.providers.error_tracker import report_provider_error

DEFAULT_CVM_BASE_URL = "https://dados.cvm.gov.br/dados"
IPE_PATH = "/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{year}.zip"
FCA_PATH = "/CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_{year}.zip"
# DFP (annual) and ITR (quarterly) statements, Phase 42.2: `dfp_cia_aberta_AAAA.zip` holds the
# main file (delivery dates), one CSV per statement and basis, and the share count.
STATEMENT_PATH = "/CIA_ABERTA/DOC/{kind}/DADOS/{lower}_cia_aberta_{year}.zip"
STATEMENT_FILES = ("BPA", "BPP", "DRE", "DFC_MI")
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


def _number(raw: str | None) -> float | None:
    try:
        return float((raw or "").strip())
    except ValueError:
        return None


def _member_rows(
    archive: zipfile.ZipFile, name: str, cnpjs: set[str] | None = None
) -> Iterable[dict[str, str]]:
    """Rows of one CSV of the archive, streamed (the files reach tens of MB).

    With `cnpjs`, rows of other companies are dropped before being turned into dicts: the
    quarterly files have millions of rows and a handful of companies is wanted.
    """
    with archive.open(name) as raw:
        reader = csv.reader(io.TextIOWrapper(raw, encoding=ENCODING), delimiter=";")
        header = next(reader, None)
        if header is None:
            return
        at = header.index("CNPJ_CIA") if "CNPJ_CIA" in header else None
        for values in reader:
            if cnpjs is not None and at is not None and values[at] not in cnpjs:
                continue
            yield dict(zip(header, values, strict=False))


def _formatted(cnpj: str) -> str:
    """The CNPJ as the CVM writes it in the statements (84.429.695/0001-11)."""
    d = cnpj.zfill(14)
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def _find(archive: zipfile.ZipFile, suffix: str) -> str | None:
    return next((n for n in archive.namelist() if n.endswith(suffix)), None)


def parse_statements(
    content: bytes,
    kind: str,
    year: int,
    cnpjs: set[str],
    known: set[tuple[str, date, int]] = frozenset(),  # type: ignore[assignment]
) -> list[StatementFact]:
    """The metrics of the statements of `cnpjs` in a yearly DFP/ITR archive.

    Statements already stored (`known`: cnpj, reference date, version) are skipped. The
    consolidated statements win; the individual ones are read only for a company without them.
    """
    lower = kind.lower()
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        main = _find(archive, f"{lower}_cia_aberta_{year}.csv")
        if main is None:
            return []
        written = {_formatted(c) for c in cnpjs}
        docs: dict[tuple[str, date, int], StatementDoc] = {}
        for row in _member_rows(archive, main, written):
            cnpj = normalize_cnpj(row.get("CNPJ_CIA") or "")
            ref, delivered = _date(row.get("DT_REFER")), _date(row.get("DT_RECEB"))
            try:
                version = int((row.get("VERSAO") or "1").strip() or 1)
            except ValueError:
                continue
            if cnpj not in cnpjs or ref is None or delivered is None:
                continue
            key = (cnpj, ref, version)
            if key not in known:
                docs[key] = StatementDoc(cnpj, kind, ref, version, delivered)
        if not docs:
            return []

        shares: dict[tuple[str, date, int], float] = {}
        capital = _find(archive, f"composicao_capital_{year}.csv")
        if capital:
            for row in _member_rows(archive, capital, written):
                key = _key(row)
                if key in docs:
                    total = _number(row.get("QT_ACAO_TOTAL_CAP_INTEGR")) or 0.0
                    treasury = _number(row.get("QT_ACAO_TOTAL_TESOURO")) or 0.0
                    if total > 0:
                        shares[key] = total - treasury

        facts: list[StatementFact] = []
        done: set[tuple[str, date, int]] = set()
        for basis, suffix in ((CONSOLIDATED, "con"), (INDIVIDUAL, "ind")):
            pending = {_formatted(k[0]) for k in docs if k not in done}
            if not pending:
                break
            rows: dict[tuple[str, date, int], list[AccountRow]] = {}
            for statement in STATEMENT_FILES:
                name = _find(archive, f"_{statement}_{suffix}_{year}.csv")
                if name is None:
                    continue
                for row in _member_rows(archive, name, pending):
                    key = _key(row)
                    if key not in docs or key in done:
                        continue
                    account = _account(row, key)
                    if account is not None and needed(account.code):
                        rows.setdefault(key, []).append(account)
            for key, accounts in rows.items():
                found = extract_facts(docs[key], basis, accounts, shares.get(key))
                if found:
                    facts.extend(found)
                    done.add(key)
        return facts


def _key(row: dict[str, str]) -> tuple[str, date, int] | None:
    ref = _date(row.get("DT_REFER"))
    try:
        version = int((row.get("VERSAO") or "1").strip() or 1)
    except ValueError:
        return None
    if ref is None:
        return None
    return (normalize_cnpj(row.get("CNPJ_CIA") or ""), ref, version)


def _account(row: dict[str, str], key: tuple[str, date, int]) -> AccountRow | None:
    value = _number(row.get("VL_CONTA"))
    end = _date(row.get("DT_FIM_EXERC"))
    code = (row.get("CD_CONTA") or "").strip()
    if value is None or end is None or not code:
        return None
    scale = SCALES.get((row.get("ESCALA_MOEDA") or "").strip().upper(), 1.0)
    return AccountRow(
        cnpj=key[0],
        reference_date=key[1],
        version=key[2],
        order=(row.get("ORDEM_EXERC") or "").strip(),
        period_start=_date(row.get("DT_INI_EXERC")),
        period_end=end,
        code=code,
        name=(row.get("DS_CONTA") or "").strip(),
        value=value * scale,
    )


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

    def _statement_url(self, kind: str, year: int) -> str:
        path = STATEMENT_PATH.format(kind=kind.upper(), lower=kind.lower(), year=year)
        return f"{self.base_url}{path}"

    def statement_stamp(self, kind: str, year: int) -> str | None:
        """Last-Modified of the yearly DFP/ITR file; None when it does not exist (yet)."""
        url = self._statement_url(kind, year)
        try:
            resp = self._client.head(url)
        except Exception as exc:
            report_provider_error(
                provider=self.PROVIDER_NAME,
                operation=kind.lower(),
                target=str(year),
                request_url=url,
                exc=exc,
            )
            return None
        if resp.status_code == 404:
            return None
        return resp.headers.get("last-modified") or resp.headers.get("etag") or "unknown"

    def statements(
        self, kind: str, year: int, cnpjs: set[str], known: set[tuple[str, date, int]]
    ) -> list[StatementFact] | None:
        """Metrics of the DFP/ITR statements of `year` for `cnpjs`; None when unavailable."""
        url = self._statement_url(kind, year)
        content = self._download(url, kind.lower(), str(year))
        if content is None:
            return None
        try:
            return parse_statements(content, kind.upper(), year, cnpjs, known)
        except zipfile.BadZipFile as exc:
            report_provider_error(
                provider=self.PROVIDER_NAME,
                operation=kind.lower(),
                target=str(year),
                request_url=url,
                exc=exc,
            )
            return None
