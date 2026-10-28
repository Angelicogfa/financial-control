"""Tesouro Direto / Tesouro Transparente (STN) provider for Brazilian Treasury bonds.

Supports both:
1. The official real-time Tesouro Direto CSV feeds (`rendimento-investir-csv` and
   `rendimento-resgatar-csv` on `www.tesourodireto.com.br`), which are lightweight (~6 KB)
   and not blocked by F5 BIG-IP JS challenges.
2. The historical CKAN CSV (`PrecoTaxaTesouroDireto.csv` on `tesourotransparente.gov.br`).
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any

import httpx

from domain.market.entities import TreasuryBond, TreasuryCatalogResult
from domain.market.services.treasury_prices import TreasuryPricePoint, bond_family
from domain.shared.enums import (
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    FixedIncomeLiquidity,
)
from infra.providers.error_tracker import report_provider_error

DEFAULT_TESOURO_CSV_URL = (
    "https://www.tesourodireto.com.br/documents/d/guest/rendimento-investir-csv?download=true"
)
DEFAULT_TESOURO_REDEEM_CSV_URL = (
    "https://www.tesourodireto.com.br/documents/d/guest/rendimento-resgatar-csv?download=true"
)

DEFAULT_TESOURO_HISTORY_CSV_URL = (
    "https://www.tesourotransparente.gov.br/ckan/dataset/"
    "df56aa42-484a-4a59-8184-7676580c81e3/resource/"
    "796d2059-14e9-44e3-80c9-2d9e30b405c1/download/PrecoTaxaTesouroDireto.csv"
)

_STALE_BASE_DATE_DAYS = 45
_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_TRAILING_YEAR_RE = re.compile(r"\s+\d{4}$")
_RATE_PCT_RE = re.compile(r"([-+]?\d+(?:[.,]\d+)?)\s*%")


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
    """Map a Tesouro `Tipo Titulo` / `Título` string to domain fixed-income metadata."""
    upper = _strip_accents(bond_type).strip().upper()
    coupon_type = "semestral" if ("JUROS SEMESTRAIS" in upper or "SEMESTRAL" in upper) else "zero"

    if "SELIC" in upper or "LFT" in upper or "RESERVA" in upper:
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
    cleaned = raw.replace("R$", "").replace("\xa0", " ").strip()
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    if not cleaned:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if positive_only and value <= 0:
        return None
    return value


def _parse_rate_expression(raw: str | None) -> float | None:
    """Extract the numeric annual rate from strings like `'SELIC + 0,0992%'`, `'IPCA + 7,80%'`,
    `'15,26%'`, or plain `'0,10'`."""
    if not raw:
        return None
    text = raw.strip()
    match = _RATE_PCT_RE.search(text)
    if match:
        return _parse_br_float(match.group(1))
    if "SELIC" in text.upper():
        return 0.0
    return _parse_br_float(text)


def _decode_csv_bytes(raw_bytes: bytes) -> str:
    body = raw_bytes.removeprefix(b"\xef\xbb\xbf")
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return body.decode("latin-1", errors="replace")


def _looks_like_html_or_invalid_csv(text: str) -> bool:
    stripped = text.lstrip("\ufeff").lstrip()
    if not stripped or stripped.startswith("<"):
        return True
    first_line = _strip_accents(stripped.splitlines()[0]).lower()
    if ";" not in first_line:
        return True
    return (
        "tipo titulo" not in first_line
        and "rendimento anual" not in first_line
        and "titulo;" not in first_line
    )


def _contracted_rate_for(
    indexer: FixedIncomeIndexer, buy_rate: float | None, sell_rate: float | None
) -> float:
    ref_rate = buy_rate if buy_rate is not None and buy_rate > 0 else sell_rate
    if indexer == FixedIncomeIndexer.SELIC:
        return 100.0
    if ref_rate is not None and ref_rate > 0:
        return round(ref_rate, 4)
    return 12.0 if indexer == FixedIncomeIndexer.PRE else 6.0


def _parse_ckan_historical_csv(
    reader: csv.DictReader[str],
    header_map: dict[str, str],
    *,
    reference_date: date | None,
    timestamp: datetime,
) -> list[TreasuryBond]:
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
        buy_price = _parse_br_float(row.get(col_buy_pu) if col_buy_pu else None, positive_only=True)
        sell_price = _parse_br_float(
            row.get(col_sell_pu) if col_sell_pu else None, positive_only=True
        )
        base_price = _parse_br_float(
            row.get(col_base_pu) if col_base_pu else None, positive_only=True
        )

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
                contracted_rate_percent=_contracted_rate_for(indexer, buy_rate, sell_rate),
                liquidity=liquidity,
                source=TesouroTransparenteProvider.PROVIDER_NAME,
                updated_at=timestamp,
            )
        )

    bonds.sort(key=lambda b: (b.maturity_date, b.symbol))
    return bonds


def _find_column(header_map: dict[str, str], *keywords: str) -> str | None:
    for norm_name, raw_name in header_map.items():
        if all(kw in norm_name for kw in keywords):
            return raw_name
    return None


def _parse_direct_daily_csv(
    reader: csv.DictReader[str],
    header_map: dict[str, str],
    *,
    reference_date: date | None,
    timestamp: datetime,
) -> list[TreasuryBond]:
    """Parse `rendimento-investir-csv` or `rendimento-resgatar-csv` from `tesourodireto.com.br`."""
    col_title = header_map.get("titulo") or (reader.fieldnames[0] if reader.fieldnames else None)
    col_rate = _find_column(header_map, "rendimento anual")
    col_maturity = _find_column(header_map, "vencimento")
    col_buy_pu = _find_column(header_map, "investimento", "pre")
    col_sell_pu = _find_column(header_map, "resgate", "pre")

    if not col_title or not col_maturity:
        return []

    base_date = reference_date or timestamp.date()
    is_redeem_feed = col_sell_pu is not None and col_buy_pu is None
    bonds: list[TreasuryBond] = []

    for row in reader:
        name = (row.get(col_title) or "").strip()
        maturity = _parse_br_date(row.get(col_maturity))
        if not name or maturity is None or maturity < base_date:
            continue

        bond_type = _TRAILING_YEAR_RE.sub("", name).strip() or name
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

        rate_val = _parse_rate_expression(row.get(col_rate) if col_rate else None)
        buy_rate = None if is_redeem_feed else rate_val
        sell_rate = rate_val if is_redeem_feed else None
        buy_price = _parse_br_float(row.get(col_buy_pu) if col_buy_pu else None, positive_only=True)
        sell_price = _parse_br_float(
            row.get(col_sell_pu) if col_sell_pu else None, positive_only=True
        )

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
                base_price=sell_price or buy_price,
                rate_type=rate_type,
                rate_unit=rate_unit,
                rate_description=rate_description,
                contracted_rate_percent=_contracted_rate_for(indexer, buy_rate, sell_rate),
                liquidity=liquidity,
                source=TesouroTransparenteProvider.PROVIDER_NAME,
                updated_at=timestamp,
            )
        )

    bonds.sort(key=lambda b: (b.maturity_date, b.symbol))
    return bonds


def merge_invest_and_redeem_bonds(
    invest_bonds: list[TreasuryBond],
    redeem_bonds: list[TreasuryBond],
) -> list[TreasuryBond]:
    """Combine investment (`rendimento-investir-csv`) and redemption (`rendimento-resgatar-csv`)
    feeds into a single catalog with both buy and sell rates/prices."""
    by_symbol: dict[str, TreasuryBond] = {b.symbol: b for b in invest_bonds}
    for redeem in redeem_bonds:
        existing = by_symbol.get(redeem.symbol)
        if existing is None:
            by_symbol[redeem.symbol] = redeem
        else:
            sell_rate = redeem.sell_rate if redeem.sell_rate is not None else existing.sell_rate
            sell_price = redeem.sell_price if redeem.sell_price is not None else existing.sell_price
            by_symbol[redeem.symbol] = replace(
                existing,
                sell_rate=sell_rate,
                sell_price=sell_price,
                base_price=sell_price or existing.base_price,
                contracted_rate_percent=_contracted_rate_for(
                    existing.indexer, existing.buy_rate, sell_rate
                ),
            )
    merged = list(by_symbol.values())
    merged.sort(key=lambda b: (b.maturity_date, b.symbol))
    return merged


def parse_tesouro_transparente_csv(
    csv_text: str,
    *,
    reference_date: date | None = None,
    fetched_at: datetime | None = None,
) -> list[TreasuryBond]:
    """Parse either the daily `tesourodireto.com.br` CSV (`Título;Rendimento anual...`) or the
    historical CKAN `PrecoTaxaTesouroDireto.csv` (`Tipo Titulo;Data Vencimento...`)."""
    cleaned = csv_text.lstrip("\ufeff")
    if _looks_like_html_or_invalid_csv(cleaned):
        return []

    timestamp = fetched_at or datetime.now(UTC)
    reader = csv.DictReader(io.StringIO(cleaned), delimiter=";")
    if not reader.fieldnames:
        return []

    header_map: dict[str, str] = {}
    for field_name in reader.fieldnames:
        if field_name:
            norm = _strip_accents(field_name).strip().lower()
            header_map[norm] = field_name

    if "tipo titulo" in header_map:
        return _parse_ckan_historical_csv(
            reader, header_map, reference_date=reference_date, timestamp=timestamp
        )
    if "titulo" in header_map or _find_column(header_map, "rendimento anual") is not None:
        return _parse_direct_daily_csv(
            reader, header_map, reference_date=reference_date, timestamp=timestamp
        )
    return []


def parse_price_history_csv(
    csv_text: str,
    *,
    families: set[str] | None = None,
    since: date | None = None,
) -> list[TreasuryPricePoint]:
    """Every daily row of `PrecoTaxaTesouroDireto.csv` (optionally only some bond families)."""
    cleaned = csv_text.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(cleaned), delimiter=";")
    if not reader.fieldnames:
        return []
    header_map = {_strip_accents(name).strip().lower(): name for name in reader.fieldnames if name}
    col_type = header_map.get("tipo titulo")
    col_maturity = header_map.get("data vencimento")
    col_base = header_map.get("data base")
    if not col_type or not col_maturity or not col_base:
        return []
    col_sell_rate = header_map.get("taxa venda manha")
    col_sell_pu = header_map.get("pu venda manha")
    col_buy_rate = header_map.get("taxa compra manha")
    col_buy_pu = header_map.get("pu compra manha")

    points: list[TreasuryPricePoint] = []
    for row in reader:
        bond_type = (row.get(col_type) or "").strip()
        if not bond_type or (families is not None and bond_family(bond_type) not in families):
            continue
        base_date = _parse_br_date(row.get(col_base))
        maturity = _parse_br_date(row.get(col_maturity))
        if base_date is None or maturity is None or (since is not None and base_date < since):
            continue
        points.append(
            TreasuryPricePoint(
                bond_type=bond_type,
                maturity_date=maturity,
                base_date=base_date,
                sell_price=_parse_br_float(
                    row.get(col_sell_pu) if col_sell_pu else None, positive_only=True
                ),
                sell_rate=_parse_br_float(row.get(col_sell_rate) if col_sell_rate else None),
                buy_price=_parse_br_float(
                    row.get(col_buy_pu) if col_buy_pu else None, positive_only=True
                ),
                buy_rate=_parse_br_float(row.get(col_buy_rate) if col_buy_rate else None),
            )
        )
    return points


class TesouroTransparenteProvider:
    """HTTP client for the official Tesouro Direto / Tesouro Transparente CSV datasets."""

    PROVIDER_NAME = "tesouro_transparente"

    def __init__(
        self,
        csv_url: str = DEFAULT_TESOURO_CSV_URL,
        redeem_csv_url: str | None = DEFAULT_TESOURO_REDEEM_CSV_URL,
        history_csv_url: str = DEFAULT_TESOURO_HISTORY_CSV_URL,
        client: httpx.Client | None = None,
        timeout: float = 30.0,
    ) -> None:
        cleaned_url = csv_url.strip() or DEFAULT_TESOURO_CSV_URL
        if client is None and "tesourotransparente.gov.br" in cleaned_url:
            cleaned_url = DEFAULT_TESOURO_CSV_URL
        self.csv_url = cleaned_url
        self.redeem_csv_url = redeem_csv_url
        self.history_csv_url = history_csv_url.strip() or DEFAULT_TESOURO_HISTORY_CSV_URL
        self._custom_client = client is not None
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=True)

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "text/csv,application/octet-stream;q=0.9,*/*;q=0.8",
        }

    def _download_csv_text(self, url: str) -> str:
        resp = self._client.get(url, headers=self._headers())
        resp.raise_for_status()
        text = _decode_csv_bytes(resp.content)
        if _looks_like_html_or_invalid_csv(text):
            raise ValueError("Tesouro endpoint returned HTML challenge or invalid CSV header")
        return text

    def list_treasury_bonds(
        self,
        *,
        reference_date: date | None = None,
    ) -> TreasuryCatalogResult:
        """Download and parse the latest Tesouro Direto catalog."""
        now = datetime.now(UTC)
        primary_url = self.csv_url
        try:
            csv_text = self._download_csv_text(primary_url)
        except Exception as exc:
            last_exc: Exception | None = exc
            # If the user's .env still has the CKAN URL blocked by WAF and we are not in a mocked
            # unit test, automatically fall back to the direct tesourodireto.com.br CSV feed.
            if not self._custom_client and primary_url != DEFAULT_TESOURO_CSV_URL:
                try:
                    primary_url = DEFAULT_TESOURO_CSV_URL
                    csv_text = self._download_csv_text(primary_url)
                except Exception as fallback_exc:
                    last_exc = fallback_exc
                else:
                    last_exc = None
            if last_exc is not None:
                report_provider_error(
                    provider=self.PROVIDER_NAME,
                    operation="treasury_catalog",
                    target="TESOURO_DIRETO",
                    request_url=primary_url,
                    exc=last_exc,
                )
                return TreasuryCatalogResult(
                    results=[],
                    unavailable_reason=(
                        "Não foi possível baixar o catálogo oficial do Tesouro Direto no momento."
                    ),
                )

        bonds = parse_tesouro_transparente_csv(
            csv_text,
            reference_date=reference_date,
            fetched_at=now,
        )

        # When pulling the direct investment CSV from tesourodireto.com.br, also enrich with the
        # redemption CSV so sell_rate / sell_price and redemption-only bonds are included.
        if (
            not self._custom_client
            and self.redeem_csv_url
            and "rendimento-investir-csv" in primary_url
        ):
            try:
                redeem_text = self._download_csv_text(self.redeem_csv_url)
                redeem_bonds = parse_tesouro_transparente_csv(
                    redeem_text,
                    reference_date=reference_date,
                    fetched_at=now,
                )
                if redeem_bonds:
                    bonds = merge_invest_and_redeem_bonds(bonds, redeem_bonds)
            except Exception:
                pass

        return TreasuryCatalogResult(results=bonds)

    def list_price_history(
        self, *, families: set[str] | None = None, since: date | None = None
    ) -> list[TreasuryPricePoint]:
        """Daily redemption prices and rates of every bond since 2002 (about 15 MB).

        A failure is reported to the worker request log and returns an empty list.
        """
        try:
            text = self._download_csv_text(self.history_csv_url)
        except Exception as exc:
            report_provider_error(
                provider=self.PROVIDER_NAME,
                operation="treasury_price_history",
                target="TESOURO_DIRETO",
                request_url=self.history_csv_url,
                exc=exc,
            )
            return []
        return parse_price_history_csv(text, families=families, since=since)
