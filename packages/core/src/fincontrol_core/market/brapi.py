"""Brapi.dev market data provider for B3 assets (Brazilian stocks, FIIs, ETFs, BDRs)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import httpx

from fincontrol_core.fundamentals.history import FundamentalPeriod, FundamentalSnapshot
from fincontrol_core.market.models import (
    Fundamentals,
    PricePoint,
    Quote,
    QuoteFreshness,
    financial_volume,
)

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
        except Exception:
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
        except Exception:
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

    def get_annual_statements(self, symbol: str) -> list[FundamentalSnapshot]:
        """Yearly statement history for a B3 symbol (empty when unavailable)."""
        clean = symbol.strip().upper().removesuffix(".SA")
        params = {"modules": "incomeStatementHistory,balanceSheetHistory,cashflowHistory"}
        try:
            resp = self._client.get(
                f"{self.base_url}/quote/{clean}", params=params, headers=self._headers()
            )
            resp.raise_for_status()
            results = resp.json().get("results") or []
        except Exception:
            return []
        return parse_brapi_statements(clean, results[0]) if results else []

    def get_fundamentals(self, symbol: str) -> Fundamentals | None:
        """Fetch fundamental indicators for B3 stocks/FIIs from brapi.dev."""
        clean = symbol.strip().upper().removesuffix(".SA")
        url = f"{self.base_url}/quote/{clean}"
        params = {
            "fundamental": "true",
            "modules": "defaultKeyStatistics,financialData,summaryDetail,summaryProfile",
        }
        try:
            resp = self._client.get(url, params=params, headers=self._headers())
            resp.raise_for_status()
            payload = resp.json()
        except Exception:
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
