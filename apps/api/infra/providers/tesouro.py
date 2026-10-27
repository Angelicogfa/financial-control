"""Tesouro Transparente (STN) provider for Brazilian Treasury bonds (Tesouro Direto).

Fetches the official open-data CSV (`PrecoTaxaTesouroDireto.csv`) published by the National
Treasury (Secretaria do Tesouro Nacional) on CKAN and extracts the latest snapshot of each
active bond.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from datetime import UTC, date, datetime
from typing import Any

import httpx

from domain.market.entities import TreasuryBond, TreasuryCatalogResult
from domain.shared.enums import (
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    FixedIncomeLiquidity,
)
from infra.providers.error_tracker import report_provider_error

DEFAULT_TESOURO_CSV_URL = (
    "https://www.tesourotransparente.gov.br/ckan/dataset/"
    "df56aa42-484a-4a59-8184-7676580c81e3/resource/"
    "796d2059-14e9-44e3-80c9-2d9e30b405c1/download/PrecoTaxaTesouroDireto.csv"
)

_STALE_BASE_DATE_DAYS = 45
_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def slugify_treasury_symbol(bond_type: str, maturity_date: date) -> str:
    """Build a deterministic slug symbol such as `tesouro-selic-01032031`."""
    ascii_name = _strip_accents(bond_type).lower().replace("+", "")
    slug = _SLUG_NON_ALNUM.sub("-", ascii_name).strip("-")
    return f"{slug}-{maturity_date.strftime('%d%m%Y')}"


def classify_tesouro_bond_type(
    bond_type: str,
) -> tuple[
    FixedIncomeInstrumentKind,
    FixedIncomeIndexer,
    str,
    str,
    FixedIncomeLiquidity,
    str,
    str,
    str,
]:
    """Map a Tesouro Transparente `Tipo Titulo` string to domain fixed-income metadata."""
    upper = _strip_accents(bond_type).strip().upper()
    coupon_type = "semestral" if ("JUROS SEMESTRAIS" in upper or "SEMESTRAL" in upper) else "zero"

    if "SELIC" in upper or "LFT" in upper:
        return (
            FixedIncomeInstrumentKind.TESOURO_SELIC,
            FixedIncomeIndexer.SELIC,
            "selic",
            coupon_type,
            FixedIncomeLiquidity.DAILY,
            "spreadOverSelic",
            "% a.a.",
            "Spread sobre a taxa Selic.",
        )
    if "PREFIXADO" in upper or "LTN" in upper or "NTN-F" in upper:
        return (
            FixedIncomeInstrumentKind.TESOURO_PRE,
            FixedIncomeIndexer.PRE,
            "prefixado",
            coupon_type,
            FixedIncomeLiquidity.AT_MATURITY,
            "nominalAnnualRate",
            "% a.a.",
            "Taxa nominal anual contratada.",
        )
    raw_indexer = "igpm" if "IGPM" in upper or "IGP-M" in upper else "ipca"
    return (
        FixedIncomeInstrumentKind.TESOURO_IPCA,
        FixedIncomeIndexer.IPCA,
        raw_indexer,
        coupon_type,
        FixedIncomeLiquidity.AT_MATURITY,
        "realAnnualRateOverIpca",
        "% a.a.",
        "Taxa real anual acima do IPCA.",
    )


def _parse_br_date(raw: str | None) -> date | None:
    if not raw:
        return None
    text = raw.strip()
    if len(text) == 10 and text[2] == "/" and text[5] == "/":
        try:
            day = int(text[0:2])
            month = int(text[3:5])
            year = int(text[6:10])
            return date(year, month, day)
        except ValueError:
            return None
    if len(text) >= 10 and text[4] == "-":
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
    return None


def _parse_br_float(raw: str | None, *, positive_only: bool = False) -> float | None:
    if not raw:
        return None
    cleaned = raw.strip().replace(".", "").replace(",", ".") if "," in raw else raw.strip()
    if not cleaned:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if positive_only and value <= 0:
        return None
    return value


def _looks_like_html_or_invalid_csv(text: str) -> bool:
    stripped = text.lstrip()
    if not stripped or stripped.startswith("<"):
        return True
    first_line = _strip_accents(stripped.splitlines()[0]).lower()
    return "tipo titulo" not in first_line or ";" not in first_line


def parse_tesouro_transparente_csv(
    csv_text: str,
    *,
    reference_date: date | None = None,
    fetched_at: datetime | None = None,
) -> list[TreasuryBond]:
    """Parse `PrecoTaxaTesouroDireto.csv` and return the latest snapshot of each active bond."""
    if _looks_like_html_or_invalid_csv(csv_text):
        return []

    timestamp = fetched_at or datetime.now(UTC)
    reader = csv.DictReader(io.StringIO(csv_text), delimiter=";")
    if not reader.fieldnames:
        return []

    # Map normalized header names to actual fieldnames in the CSV
    header_map: dict[str, str] = {}
    for field_name in reader.fieldnames:
        if field_name:
            norm = _strip_accents(field_name).strip().lower()
            header_map[norm] = field_name

    col_type = header_map.get("tipo titulo")
    col_maturity = header_map.get("data vencimento")
    col_base = header_map.get("data base")
    col_buy_rate = header_map.get("taxa compra manha")
    col_sell_rate = header_map.get("taxa venda manha")
    col_buy_pu = header_map.get("pu compra manha")
    col_sell_pu = header_map.get("pu venda manha")
    col_base_pu = header_map.get("pu base manha")

    if not col_type or not col_maturity or not col_base:
        return []

    latest_by_key: dict[tuple[str, date], tuple[date, dict[str, Any]]] = {}
    max_base_date: date | None = None

    for row in reader:
        bond_type = (row.get(col_type) or "").strip()
        maturity = _parse_br_date(row.get(col_maturity))
        base_date = _parse_br_date(row.get(col_base))
        if not bond_type or maturity is None or base_date is None:
            continue
        if max_base_date is None or base_date > max_base_date:
            max_base_date = base_date
        key = (bond_type, maturity)
        existing = latest_by_key.get(key)
        if existing is None or base_date >= existing[0]:
            latest_by_key[key] = (base_date, row)

    if not latest_by_key or max_base_date is None:
        return []

    cutoff_date = reference_date or max_base_date
    bonds: list[TreasuryBond] = []

    for (bond_type, maturity), (base_date, row) in latest_by_key.items():
        if maturity < cutoff_date:
            continue
        if (max_base_date - base_date).days > _STALE_BASE_DATE_DAYS:
            continue

        (
            instrument_kind,
            indexer,
            raw_indexer,
            coupon_type,
            liquidity,
            rate_type,
            rate_unit,
            rate_description,
        ) = classify_tesouro_bond_type(bond_type)

        buy_rate = _parse_br_float(row.get(col_buy_rate) if col_buy_rate else None)
        sell_rate = _parse_br_float(row.get(col_sell_rate) if col_sell_rate else None)
        buy_price = _parse_br_float(
            row.get(col_buy_pu) if col_buy_pu else None, positive_only=True
        )
        sell_price = _parse_br_float(
            row.get(col_sell_pu) if col_sell_pu else None, positive_only=True
        )
        base_price = _parse_br_float(
            row.get(col_base_pu) if col_base_pu else None, positive_only=True
        )

        ref_rate = buy_rate if buy_rate is not None and buy_rate > 0 else sell_rate
        if indexer == FixedIncomeIndexer.SELIC:
            contracted_rate_percent = 100.0
        elif ref_rate is not None and ref_rate > 0:
            contracted_rate_percent = round(ref_rate, 4)
        else:
            contracted_rate_percent = 12.0 if indexer == FixedIncomeIndexer.PRE else 6.0

        year_str = str(maturity.year)
        name = bond_type if year_str in bond_type else f"{bond_type} {year_str}"
        symbol = slugify_treasury_symbol(bond_type, maturity)
        duration_days = max((maturity - base_date).days, 0)

        bonds.append(
            TreasuryBond(
                symbol=symbol,
                name=name,
                bond_type=bond_type,
                instrument_kind=instrument_kind,
                indexer=indexer,
                raw_indexer=raw_indexer,
                coupon_type=coupon_type,
                maturity_date=maturity,
                duration_days=duration_days,
                base_date=base_date,
                buy_rate=buy_rate,
                sell_rate=sell_rate,
                buy_price=buy_price,
                sell_price=sell_price,
                base_price=base_price,
                rate_type=rate_type,
                rate_unit=rate_unit,
                rate_description=rate_description,
                contracted_rate_percent=contracted_rate_percent,
                liquidity=liquidity,
                source=TesouroTransparenteProvider.PROVIDER_NAME,
                updated_at=timestamp,
            )
        )

    bonds.sort(key=lambda b: (b.maturity_date, b.symbol))
    return bonds


class TesouroTransparenteProvider:
    """HTTP client for the official Tesouro Transparente CSV dataset."""

    PROVIDER_NAME = "tesouro_transparente"

    def __init__(
        self,
        csv_url: str = DEFAULT_TESOURO_CSV_URL,
        client: httpx.Client | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.csv_url = csv_url.strip() or DEFAULT_TESOURO_CSV_URL
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=True)

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "text/csv,application/octet-stream;q=0.9,*/*;q=0.8",
        }

    def list_treasury_bonds(
        self,
        *,
        reference_date: date | None = None,
    ) -> TreasuryCatalogResult:
        """Download and parse the latest Tesouro Direto catalog from Tesouro Transparente."""
        try:
            resp = self._client.get(self.csv_url, headers=self._headers())
            resp.raise_for_status()
        except Exception as exc:
            report_provider_error(
                provider=self.PROVIDER_NAME,
                operation="treasury_catalog",
                target="TESOURO_DIRETO",
                request_url=self.csv_url,
                exc=exc,
            )
            return TreasuryCatalogResult(
                results=[],
                unavailable_reason=(
                    "Não foi possível baixar o catálogo oficial do Tesouro Transparente no momento."
                ),
            )

        raw_bytes = resp.content
        try:
            csv_text = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            csv_text = raw_bytes.decode("latin-1", errors="replace")

        if _looks_like_html_or_invalid_csv(csv_text):
            err = ValueError("Tesouro Transparente returned HTML challenge or invalid CSV header")
            report_provider_error(
                provider=self.PROVIDER_NAME,
                operation="treasury_catalog",
                target="TESOURO_DIRETO",
                request_url=self.csv_url,
                exc=err,
            )
            return TreasuryCatalogResult(
                results=[],
                unavailable_reason=(
                    "O portal do Tesouro Transparente retornou uma resposta inválida "
                    "ou bloqueio temporário."
                ),
            )

        bonds = parse_tesouro_transparente_csv(
            csv_text,
            reference_date=reference_date,
            fetched_at=datetime.now(UTC),
        )
        return TreasuryCatalogResult(results=bonds)
