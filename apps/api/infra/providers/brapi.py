"""Brapi.dev market data provider for B3 assets (Brazilian stocks, FIIs, ETFs, BDRs)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import httpx

from domain.assets.services.history import FundamentalPeriod, FundamentalSnapshot
from domain.market.entities import (
    Fundamentals,
    PricePoint,
    Quote,
    QuoteFreshness,
    TreasuryBond,
    TreasuryCatalogResult,
    financial_volume,
)
from domain.shared.entities import CatalogInstrument
from domain.shared.enums import (
    AssetType,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    FixedIncomeLiquidity,
)
from infra.providers.error_tracker import report_provider_error

# Units of the quoteSummary fields consumed from brapi (ADR 0006): returnOnEquity,
# profitMargins, revenueGrowth, earningsGrowth and dividendYield are fractions;
# debtToEquity is a percentage; averageDailyVolume10Day is a share count.


def _float_or_none(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, dict) and "raw" in val:
        val = val["raw"]
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


class BrapiProvider:
    """HTTP client for https://brapi.dev/api."""

    PROVIDER_NAME = "brapi"

    def __init__(
        self,
        token: str | None = None,
        base_url: str = "https://brapi.dev/api",
        client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.token = token.strip() if token else None
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout)

    def _headers(self) -> dict[str, str]:
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    def get_quote(self, symbol: str) -> Quote | None:
        """Fetch live quote for a single B3 symbol."""
        clean = symbol.strip().upper().removesuffix(".SA")
        url = f"{self.base_url}/quote/{clean}"
        try:
            resp = self._client.get(url, headers=self._headers())
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            report_provider_error(
                provider=self.PROVIDER_NAME,
                operation="quote",
                target=clean,
                request_url=url,
                exc=exc,
            )
            return None

        results = payload.get("results") or []
        if not results:
            return None
        item = results[0]
        price = _float_or_none(item.get("regularMarketPrice"))
        if price is None or price <= 0:
            return None

        market_time: datetime | None = None
        raw_time = item.get("regularMarketTime")
        if isinstance(raw_time, str):
            try:
                market_time = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
            except ValueError:
                market_time = None
        elif isinstance(raw_time, int | float):
            market_time = datetime.fromtimestamp(float(raw_time), tz=UTC)

        return Quote(
            symbol=clean,
            price=price,
            currency=str(item.get("currency") or "BRL"),
            name=item.get("longName") or item.get("shortName") or clean,
            change_pct=_float_or_none(item.get("regularMarketChangePercent")),
            previous_close=_float_or_none(item.get("regularMarketPreviousClose")),
            day_high=_float_or_none(item.get("regularMarketDayHigh")),
            day_low=_float_or_none(item.get("regularMarketDayLow")),
            volume=_float_or_none(item.get("regularMarketVolume")),
            fifty_two_week_high=_float_or_none(item.get("fiftyTwoWeekHigh")),
            fifty_two_week_low=_float_or_none(item.get("fiftyTwoWeekLow")),
            market_cap=_float_or_none(item.get("marketCap")),
            logo_url=item.get("logourl"),
            market_time=market_time,
            provider=self.PROVIDER_NAME,
            freshness=QuoteFreshness.LIVE,
        )

    def get_history(self, symbol: str, range_period: str = "1y") -> list[PricePoint]:
        """Fetch daily historical OHLCV points from brapi.dev."""
        clean = symbol.strip().upper().removesuffix(".SA")
        url = f"{self.base_url}/quote/{clean}"
        params = {"range": range_period, "interval": "1d"}
        try:
            resp = self._client.get(url, params=params, headers=self._headers())
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            report_provider_error(
                provider=self.PROVIDER_NAME,
                operation="history",
                target=f"{clean} ({range_period})",
                request_url=f"{url}?range={range_period}&interval=1d",
                exc=exc,
            )
            return []

        results = payload.get("results") or []
        if not results:
            return []
        hist_raw = results[0].get("historicalDataPrice") or []
        points: list[PricePoint] = []
        for row in hist_raw:
            close_val = _float_or_none(row.get("close"))
            raw_date = row.get("date")
            if close_val is None or raw_date is None:
                continue
            if isinstance(raw_date, int | float):
                pt_date = datetime.fromtimestamp(float(raw_date), tz=UTC).date()
            elif isinstance(raw_date, str):
                pt_date = date.fromisoformat(raw_date[:10])
            else:
                continue
            points.append(
                PricePoint(
                    date=pt_date,
                    close=close_val,
                    open=_float_or_none(row.get("open")),
                    high=_float_or_none(row.get("high")),
                    low=_float_or_none(row.get("low")),
                    adj_close=_float_or_none(row.get("adjustedClose")) or close_val,
                    volume=_float_or_none(row.get("volume")),
                )
            )
        points.sort(key=lambda p: p.date)
        return points

    def list_instruments(
        self, *, page_size: int = 100, max_pages: int = 50
    ) -> list[CatalogInstrument]:
        """Every listed B3 instrument from /quote/list (paginated); empty on failure."""
        fetched_at = datetime.now(UTC)
        instruments: dict[str, CatalogInstrument] = {}
        for page in range(1, max_pages + 1):
            url = f"{self.base_url}/quote/list"
            try:
                resp = self._client.get(
                    url,
                    params={"page": page, "limit": page_size, "sortBy": "volume"},
                    headers=self._headers(),
                )
                resp.raise_for_status()
                payload = resp.json()
            except Exception as exc:
                report_provider_error(
                    provider=self.PROVIDER_NAME,
                    operation="catalog",
                    target=f"B3 (page {page})",
                    request_url=f"{url}?page={page}&limit={page_size}&sortBy=volume",
                    exc=exc,
                )
                break
            for item in payload.get("stocks") or []:
                instrument = parse_brapi_list_item(item, fetched_at)
                if instrument is not None:
                    instruments.setdefault(instrument.ticker, instrument)
            if not payload.get("hasNextPage") or page >= int(payload.get("totalPages") or page):
                break
        return list(instruments.values())

    def list_treasury_bonds(
        self,
        *,
        indexer: str | None = None,
        coupon_type: str | None = None,
        search: str | None = None,
        sort_by: str = "maturityDate",
        sort_order: str = "asc",
        page_size: int = 100,
        max_pages: int = 10,
    ) -> TreasuryCatalogResult:
        """Fetch available Brazilian Treasury bonds from /v2/treasury/list."""
        bonds: dict[str, TreasuryBond] = {}
        for page in range(1, max_pages + 1):
            params: dict[str, Any] = {
                "page": page,
                "limit": page_size,
                "sortBy": sort_by,
                "sortOrder": sort_order,
            }
            if indexer:
                params["indexer"] = indexer
            if coupon_type:
                params["couponType"] = coupon_type
            if search:
                params["search"] = search.strip()
            try:
                resp = self._client.get(
                    f"{self.base_url}/v2/treasury/list",
                    params=params,
                    headers=self._headers(),
                )
            except Exception:
                return TreasuryCatalogResult(
                    results=list(bonds.values()),
                    unavailable_reason=(
                        "Não foi possível conectar à API de Tesouro Direto da Brapi."
                    ),
                )

            if resp.status_code in (401, 403):
                message = _extract_error_message(resp) or (
                    "A consulta de Tesouro Direto na Brapi (/api/v2/treasury/list) "
                    "requer token autenticado no plano Pro."
                )
                return TreasuryCatalogResult(results=[], unavailable_reason=message)

            try:
                resp.raise_for_status()
                payload = resp.json()
            except Exception:
                return TreasuryCatalogResult(
                    results=list(bonds.values()),
                    unavailable_reason=(
                        "A API de Tesouro Direto da Brapi retornou uma resposta inválida."
                    ),
                )

            for item in payload.get("results") or []:
                bond = parse_brapi_treasury_item(item)
                if bond is not None:
                    bonds.setdefault(bond.symbol, bond)

            pagination = payload.get("pagination") or {}
            has_next = bool(pagination.get("hasNextPage") or payload.get("hasNextPage"))
            total_pages = int(pagination.get("totalPages") or payload.get("totalPages") or page)
            if not has_next or page >= total_pages:
                break
        return TreasuryCatalogResult(results=list(bonds.values()))

    def get_annual_statements(self, symbol: str) -> list[FundamentalSnapshot]:
        """Yearly statement history for a B3 symbol (empty when unavailable)."""
        clean = symbol.strip().upper().removesuffix(".SA")
        url = f"{self.base_url}/quote/{clean}"
        modules = "incomeStatementHistory,balanceSheetHistory,cashflowHistory"
        params = {"modules": modules}
        try:
            resp = self._client.get(url, params=params, headers=self._headers())
            resp.raise_for_status()
            results = resp.json().get("results") or []
        except Exception as exc:
            report_provider_error(
                provider=self.PROVIDER_NAME,
                operation="statements",
                target=clean,
                request_url=f"{url}?modules={modules}",
                exc=exc,
            )
            return []
        return parse_brapi_statements(clean, results[0]) if results else []

    def get_fundamentals(self, symbol: str) -> Fundamentals | None:
        """Fetch fundamental indicators for B3 stocks/FIIs from brapi.dev."""
        clean = symbol.strip().upper().removesuffix(".SA")
        url = f"{self.base_url}/quote/{clean}"
        modules = "defaultKeyStatistics,financialData,summaryDetail,summaryProfile"
        params = {
            "fundamental": "true",
            "modules": modules,
        }
        try:
            resp = self._client.get(url, params=params, headers=self._headers())
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            report_provider_error(
                provider=self.PROVIDER_NAME,
                operation="fundamentals",
                target=clean,
                request_url=f"{url}?fundamental=true&modules={modules}",
                exc=exc,
            )
            return None

        results = payload.get("results") or []
        if not results:
            return None
        item = results[0]
        stats = item.get("defaultKeyStatistics") or {}
        fin = item.get("financialData") or {}
        summary = item.get("summaryDetail") or {}
        profile = item.get("summaryProfile") or {}

        pe = _float_or_none(item.get("priceEarnings")) or _float_or_none(summary.get("trailingPE"))
        pb = _float_or_none(stats.get("priceToBook"))
        eps = _float_or_none(item.get("earningsPerShare")) or _float_or_none(
            stats.get("trailingEps")
        )
        bvps = _float_or_none(stats.get("bookValue"))
        dy = _float_or_none(summary.get("dividendYield")) or _float_or_none(
            stats.get("dividendYield")
        )
        dps = _float_or_none(summary.get("trailingAnnualDividendRate"))
        debt_to_eq_pct = _float_or_none(fin.get("debtToEquity"))
        price = _float_or_none(item.get("regularMarketPrice"))
        volume_shares = _float_or_none(item.get("averageDailyVolume10Day")) or _float_or_none(
            item.get("regularMarketVolume")
        )

        total_debt = _float_or_none(fin.get("totalDebt"))
        total_cash = _float_or_none(fin.get("totalCash")) or 0.0
        ebitda = _float_or_none(fin.get("ebitda"))
        net_debt_ebitda: float | None = None
        if total_debt is not None and ebitda is not None and ebitda > 0:
            net_debt_ebitda = (total_debt - total_cash) / ebitda

        return Fundamentals(
            symbol=clean,
            sector=profile.get("sector"),
            industry=profile.get("industry"),
            price_to_earnings=pe,
            price_to_book=pb,
            earnings_per_share=eps,
            book_value_per_share=bvps,
            dividend_yield=dy,
            dividends_per_share_ttm=dps,
            return_on_equity=_float_or_none(fin.get("returnOnEquity")),
            profit_margin=_float_or_none(fin.get("profitMargins")),
            debt_to_equity=debt_to_eq_pct / 100.0 if debt_to_eq_pct is not None else None,
            net_debt_to_ebitda=net_debt_ebitda,
            revenue_growth=_float_or_none(fin.get("revenueGrowth")),
            earnings_growth=_float_or_none(fin.get("earningsGrowth")),
            market_cap=_float_or_none(item.get("marketCap")),
            avg_daily_volume=financial_volume(volume_shares, price),
        )


def _statement_rows(item: dict[str, Any], module: str, inner: str) -> list[dict[str, Any]]:
    """brapi returns either a plain list or Yahoo's `{module: {inner: [...]}}` shape."""
    raw = item.get(module)
    if isinstance(raw, dict):
        raw = raw.get(inner)
    return [row for row in raw or [] if isinstance(row, dict)]


def _row_date(row: dict[str, Any]) -> date | None:
    raw = row.get("endDate")
    if isinstance(raw, dict):
        raw = raw.get("raw", raw.get("fmt"))
    if isinstance(raw, int | float):
        return datetime.fromtimestamp(float(raw), tz=UTC).date()
    if isinstance(raw, str) and len(raw) >= 10:
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None
    return None


def parse_brapi_statements(symbol: str, item: dict[str, Any]) -> list[FundamentalSnapshot]:
    """Annual snapshots from brapi's income statement, balance sheet and cash flow modules."""
    by_year: dict[date, dict[str, float | None]] = {}

    def put(rows: list[dict[str, Any]], fields: dict[str, tuple[str, ...]]) -> None:
        for row in rows:
            ref = _row_date(row)
            if ref is None:
                continue
            metrics = by_year.setdefault(ref, {})
            for key, candidates in fields.items():
                for candidate in candidates:
                    value = _float_or_none(row.get(candidate))
                    if value is not None:
                        metrics[key] = value
                        break

    put(
        _statement_rows(item, "incomeStatementHistory", "incomeStatementHistory"),
        {"revenue": ("totalRevenue",), "net_income": ("netIncome",), "ebitda": ("ebitda", "ebit")},
    )
    put(
        _statement_rows(item, "balanceSheetHistory", "balanceSheetStatements"),
        {
            "equity": ("totalStockholderEquity", "stockholdersEquity"),
            "cash": ("cash", "cashAndCashEquivalents"),
            "total_debt": ("totalDebt", "longTermDebt"),
        },
    )
    put(
        _statement_rows(item, "cashflowHistory", "cashflowStatements"),
        {"dividends_paid": ("dividendsPaid",)},
    )
    return [
        FundamentalSnapshot(
            ticker=symbol,
            reference_date=ref,
            period=FundamentalPeriod.ANNUAL,
            metrics=metrics,
            source=BrapiProvider.PROVIDER_NAME,
        )
        for ref, metrics in sorted(by_year.items())
    ]


_ETF_HINTS = ("ETF", "INDICE", "ÍNDICE", "INDEX")


def classify_brapi_type(raw_type: str | None, name: str) -> AssetType | None:
    """Map brapi's `type` (stock, fund, bdr) to an AssetType; funds split into ETF and FII."""
    kind = (raw_type or "").lower()
    if kind == "stock":
        return AssetType.STOCK_BR
    if kind == "bdr":
        return AssetType.BDR
    if kind == "fund":
        upper = name.upper()
        return AssetType.ETF_BR if any(h in upper for h in _ETF_HINTS) else AssetType.FII
    return None


def parse_brapi_list_item(item: dict[str, Any], fetched_at: datetime) -> CatalogInstrument | None:
    ticker = str(item.get("stock") or "").strip().upper()
    if not ticker:
        return None
    name = str(item.get("name") or ticker).strip()
    close = _float_or_none(item.get("close"))
    return CatalogInstrument(
        ticker=ticker,
        name=name,
        asset_type=classify_brapi_type(item.get("type"), name),
        sector=item.get("sector") or None,
        close=close,
        change_pct=(
            change / 100.0 if (change := _float_or_none(item.get("change"))) is not None else None
        ),
        volume_brl=financial_volume(_float_or_none(item.get("volume")), close),
        market_cap=_float_or_none(item.get("market_cap")),
        logo_url=item.get("logo") or None,
        updated_at=fetched_at,
    )


def _extract_error_message(resp: httpx.Response) -> str | None:
    try:
        payload = resp.json()
    except Exception:
        return None
    if isinstance(payload, dict):
        msg = payload.get("message")
        if isinstance(msg, str) and msg.strip():
            return msg.strip()
    return None


def classify_brapi_treasury_indexer(
    raw_indexer: str | None,
) -> tuple[FixedIncomeInstrumentKind, FixedIncomeIndexer, FixedIncomeLiquidity]:
    """Map brapi's treasury `indexer` (selic, prefixado, ipca, igpm) to fixed income enums."""
    kind = (raw_indexer or "").strip().lower()
    if kind == "selic":
        return (
            FixedIncomeInstrumentKind.TESOURO_SELIC,
            FixedIncomeIndexer.SELIC,
            FixedIncomeLiquidity.DAILY,
        )
    if kind in ("prefixado", "pre"):
        return (
            FixedIncomeInstrumentKind.TESOURO_PRE,
            FixedIncomeIndexer.PRE,
            FixedIncomeLiquidity.AT_MATURITY,
        )
    return (
        FixedIncomeInstrumentKind.TESOURO_IPCA,
        FixedIncomeIndexer.IPCA,
        FixedIncomeLiquidity.AT_MATURITY,
    )


def _iso_date_or_none(val: Any) -> date | None:
    if isinstance(val, str) and len(val) >= 10:
        try:
            return date.fromisoformat(val[:10])
        except ValueError:
            return None
    return None


def parse_brapi_treasury_item(item: dict[str, Any]) -> TreasuryBond | None:
    """Parse a single Treasury bond entry from `/v2/treasury/list` or `/v2/treasury/indicators`."""
    symbol = str(item.get("symbol") or "").strip().lower()
    maturity = _iso_date_or_none(item.get("maturityDate"))
    if not symbol or maturity is None:
        return None

    bond_type = str(item.get("bondType") or symbol).strip()
    year_str = str(maturity.year)
    name = bond_type if year_str in bond_type else f"{bond_type} {year_str}"
    raw_indexer = str(item.get("indexer") or "ipca").strip().lower()
    instrument_kind, indexer, liquidity = classify_brapi_treasury_indexer(raw_indexer)
    coupon_type = str(item.get("couponType") or "zero").strip().lower()

    buy_rate = _float_or_none(item.get("buyRate"))
    sell_rate = _float_or_none(item.get("sellRate"))
    ref_rate = buy_rate if buy_rate is not None and buy_rate > 0 else sell_rate
    if indexer == FixedIncomeIndexer.SELIC:
        # In the fixed income engine, SELIC contracted_rate is a multiplier of Selic (100% = 1.0).
        contracted_rate_percent = 100.0
    elif ref_rate is not None and ref_rate > 0:
        contracted_rate_percent = round(ref_rate, 4)
    else:
        contracted_rate_percent = 12.0 if indexer == FixedIncomeIndexer.PRE else 6.0

    rate_info = item.get("rateInfo") if isinstance(item.get("rateInfo"), dict) else {}
    duration_raw = item.get("durationDays")
    duration_days = int(duration_raw) if isinstance(duration_raw, int | float) else None

    return TreasuryBond(
        symbol=symbol,
        name=name,
        bond_type=bond_type,
        instrument_kind=instrument_kind,
        indexer=indexer,
        raw_indexer=raw_indexer,
        coupon_type=coupon_type,
        maturity_date=maturity,
        duration_days=duration_days,
        base_date=_iso_date_or_none(item.get("baseDate")),
        buy_rate=buy_rate,
        sell_rate=sell_rate,
        buy_price=_float_or_none(item.get("buyPrice")),
        sell_price=_float_or_none(item.get("sellPrice")),
        base_price=_float_or_none(item.get("basePrice")),
        rate_type=str(rate_info.get("rateType")) if rate_info.get("rateType") else None,
        rate_unit=str(rate_info.get("rateUnit")) if rate_info.get("rateUnit") else None,
        rate_description=(
            str(rate_info.get("description")) if rate_info.get("description") else None
        ),
        contracted_rate_percent=contracted_rate_percent,
        liquidity=liquidity,
    )
