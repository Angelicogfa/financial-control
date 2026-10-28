"""B3 listed companies and funds pages: declared dividends and stock events (item 26.3).

The public endpoints behind "Empresas listadas" on b3.com.br take a Base64 JSON argument and
return the cash distributions (dividends, JCP, FII yields) with the data com (`lastDatePrior`),
the payment date and the gross amount per share, plus the stock events (splits, reverse
splits, bonus issues). Entries come per ISIN, so the ticker class picks its own line (ON, PN,
units or fund quotas). Free and keyless, unlike brapi's paid dividends feature.
"""

from __future__ import annotations

import base64
import json
import re
from datetime import date
from typing import Any

import httpx

from domain.market.entities import (
    AnnouncedDistributions,
    AnnouncedEarning,
    AnnouncedStockEvent,
)
from domain.shared.enums import AssetType
from infra.providers.error_tracker import report_provider_error

DEFAULT_B3_LISTED_BASE_URL = "https://sistemaswebb3-listados.b3.com.br"
COMPANY_PATH = "/listedCompaniesProxy/CompanyCall/GetListedSupplementCompany/"
FUNDS_PATH = "/fundsProxy/fundsCall/GetListedSupplementFunds/"
FII_TYPE = 7

FUND_TYPES = frozenset({AssetType.FII})
COMPANY_TYPES = frozenset({AssetType.STOCK_BR, AssetType.BDR})

# Ticker class -> ISIN share-type marker (ITSA4 -> BRITSAACNPR7).
_ISIN_MARKERS: dict[int, str] = {
    3: "ACNOR",
    4: "ACNPR",
    5: "ACNPA",
    6: "ACNPB",
    7: "ACNPC",
    8: "ACNPD",
    11: "CDAM",
}
_TICKER_RE = re.compile(r"^([A-Z0-9]{4})(\d{1,2})F?$")


def _encode(payload: dict[str, Any]) -> str:
    return base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()


def _br_date(raw: Any) -> date | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if len(text) != 10 or text[2] != "/" or text[5] != "/":
        return None
    try:
        return date(int(text[6:10]), int(text[3:5]), int(text[0:2]))
    except ValueError:
        return None


def _br_float(raw: Any) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip().replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def isin_marker(ticker: str, asset_type: AssetType) -> str | None:
    """ISIN fragment of the ticker's share class (fund quotas use `CTF`)."""
    if asset_type in FUND_TYPES:
        return "CTF"
    match = _TICKER_RE.match(ticker.strip().upper())
    return _ISIN_MARKERS.get(int(match.group(2))) if match else None


def _matches(isin: str, marker: str | None) -> bool:
    return marker is None or marker in isin.upper()


def parse_supplement(ticker: str, asset_type: AssetType, payload: Any) -> AnnouncedDistributions:
    """Cash and stock distributions of `ticker` from a supplement response."""
    item = payload[0] if isinstance(payload, list) and payload else payload
    if not isinstance(item, dict):
        return AnnouncedDistributions()
    marker = isin_marker(ticker, asset_type)
    raw_cash = item.get("cashDividends") or []
    raw_stock = item.get("stockDividends") or []
    if marker and not any(_matches(str(i.get("isinCode") or ""), marker) for i in raw_cash):
        marker = None  # unknown class: keep every line, de-duplicated below

    cash: list[AnnouncedEarning] = []
    seen: set[tuple] = set()
    for entry in raw_cash:
        if not _matches(str(entry.get("isinCode") or ""), marker):
            continue
        rate = _br_float(entry.get("rate"))
        if rate is None or rate <= 0:
            continue
        earning = AnnouncedEarning(
            ticker=ticker,
            label=str(entry.get("label") or "DIVIDENDO").strip().upper(),
            rate=rate,
            com_date=_br_date(entry.get("lastDatePrior")),
            payment_date=_br_date(entry.get("paymentDate")),
            approved_on=_br_date(entry.get("approvedOn")),
            related_to=(str(entry.get("relatedTo")).strip() or None)
            if entry.get("relatedTo")
            else None,
        )
        key = (earning.label, earning.com_date, earning.payment_date, earning.rate)
        if key not in seen:
            seen.add(key)
            cash.append(earning)

    stock: list[AnnouncedStockEvent] = []
    seen_stock: set[tuple] = set()
    for entry in raw_stock:
        if not _matches(str(entry.get("isinCode") or ""), marker):
            continue
        event = AnnouncedStockEvent(
            ticker=ticker,
            label=str(entry.get("label") or "").strip().upper(),
            factor=_br_float(entry.get("factor")),
            com_date=_br_date(entry.get("lastDatePrior")),
            approved_on=_br_date(entry.get("approvedOn")),
        )
        key = (event.label, event.com_date, event.factor)
        if key not in seen_stock:
            seen_stock.add(key)
            stock.append(event)
    return AnnouncedDistributions(cash=cash, stock=stock)


class B3ListedProvider:
    """HTTP client for the B3 listed companies / funds supplement pages."""

    PROVIDER_NAME = "b3_listed"

    def __init__(
        self,
        base_url: str = DEFAULT_B3_LISTED_BASE_URL,
        client: httpx.Client | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout)

    def _url(self, ticker: str, asset_type: AssetType) -> str | None:
        match = _TICKER_RE.match(ticker.strip().upper())
        if match is None:
            return None
        issuer = match.group(1)
        if asset_type in FUND_TYPES:
            payload = {"cnpj": "0", "identifierFund": issuer, "typeFund": FII_TYPE}
            return f"{self.base_url}{FUNDS_PATH}{_encode(payload)}"
        if asset_type in COMPANY_TYPES:
            payload = {"issuingCompany": issuer, "language": "pt-br"}
            return f"{self.base_url}{COMPANY_PATH}{_encode(payload)}"
        return None

    def get_distributions(self, ticker: str, asset_type: AssetType) -> AnnouncedDistributions:
        """Declared distributions of a B3 stock, BDR or FII (empty for other types)."""
        url = self._url(ticker, asset_type)
        if url is None:
            return AnnouncedDistributions()
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
            payload = json.loads(resp.text) if resp.text.strip() else None
        except Exception as exc:
            report_provider_error(
                provider=self.PROVIDER_NAME,
                operation="distributions",
                target=ticker,
                request_url=url,
                exc=exc,
            )
            return AnnouncedDistributions()
        return parse_supplement(ticker.strip().upper(), asset_type, payload)
