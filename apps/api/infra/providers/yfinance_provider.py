"""Yahoo Finance provider for US assets, Crypto, FX (USDBRL=X), Indices, and B3 .SA fallback."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from domain.assets.services.history import FundamentalPeriod, FundamentalSnapshot
from domain.market.entities import (
    Fundamentals,
    PricePoint,
    Quote,
    QuoteFreshness,
    financial_volume,
)
from domain.shared.enums import Market

# Units of the yfinance `Ticker.info` fields consumed here (ADR 0006): returnOnEquity,
# profitMargins, revenueGrowth, earningsGrowth and trailingAnnualDividendYield are
# fractions; dividendYield and debtToEquity are percentages (yfinance >= 0.2.54);
# averageVolume is a share count.


def _use_writable_cache() -> None:
    """yfinance caches time zones under the home directory; containers run as a user without
    one, so every quote would refetch it. Point the cache at a writable temp folder."""
    import tempfile

    try:
        import yfinance as yf

        yf.set_tz_cache_location(str(Path(tempfile.gettempdir()) / "py-yfinance"))
    except Exception:  # pragma: no cover - cache is an optimization only
        pass


def resolve_yahoo_symbol(symbol: str, market: Market | None = None) -> str:
    """Normalize ticker symbol for Yahoo Finance (.SA for B3 or -USD for Crypto if needed)."""
    s = symbol.strip().upper()
    if s in ("IBOV", "^BVSP"):
        return "^BVSP"
    if s in ("IFIX", "IFIX.SA"):
        return "IFIX.SA"
    if s in ("SP500", "S&P500", "^GSPC"):
        return "^GSPC"
    if s in ("USDBRL", "USD/BRL", "USDBRL=X"):
        return "USDBRL=X"
    if market == Market.B3 and not s.endswith(".SA") and not s.startswith("^"):
        return f"{s}.SA"
    if market == Market.CRYPTO and "-" not in s:
        return f"{s}-USD"
    return s


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        num = float(val)
        return None if num != num else num  # filter NaN
    except (TypeError, ValueError):
        return None


class YFinanceProvider:
    """Market data adapter backed by `yfinance` (with injectable ticker factory for testing)."""

    PROVIDER_NAME = "yfinance"

    def __init__(self, ticker_factory: Callable[[str], Any] | None = None) -> None:
        self._ticker_factory = ticker_factory

    def _get_ticker(self, yf_sym: str) -> Any:
        if self._ticker_factory is None:
            import yfinance as yf

            _use_writable_cache()
            self._ticker_factory = yf.Ticker
        return self._ticker_factory(yf_sym)

    def get_quote(self, symbol: str, market: Market | None = None) -> Quote | None:
        """Fetch latest quote from Yahoo Finance."""
        yf_sym = resolve_yahoo_symbol(symbol, market)
        try:
            ticker_obj = self._get_ticker(yf_sym)
            info: dict[str, Any] = getattr(ticker_obj, "info", None) or {}
            price = (
                _safe_float(info.get("regularMarketPrice"))
                or _safe_float(info.get("currentPrice"))
                or _safe_float(info.get("previousClose"))
            )
            if price is None or price <= 0:
                hist = ticker_obj.history(period="5d")
                if hist is not None and not hist.empty:
                    price = _safe_float(hist["Close"].iloc[-1])
            if price is None or price <= 0:
                return None

            prev_close = _safe_float(info.get("previousClose"))
            change_pct = _safe_float(info.get("regularMarketChangePercent"))
            if change_pct is None and prev_close and prev_close > 0:
                change_pct = (price - prev_close) / prev_close * 100.0

            default_curr = "BRL" if yf_sym.endswith(".SA") or yf_sym == "^BVSP" else "USD"
            return Quote(
                symbol=symbol.strip().upper(),
                price=price,
                currency=str(info.get("currency") or default_curr),
                name=info.get("longName") or info.get("shortName") or symbol.strip().upper(),
                change_pct=change_pct,
                previous_close=prev_close,
                day_high=_safe_float(info.get("dayHigh")),
                day_low=_safe_float(info.get("dayLow")),
                volume=_safe_float(info.get("volume")),
                fifty_two_week_high=_safe_float(info.get("fiftyTwoWeekHigh")),
                fifty_two_week_low=_safe_float(info.get("fiftyTwoWeekLow")),
                market_cap=_safe_float(info.get("marketCap")),
                provider=self.PROVIDER_NAME,
                freshness=QuoteFreshness.LIVE,
            )
        except Exception:
            return None

    def get_history(
        self,
        symbol: str,
        range_period: str = "1y",
        market: Market | None = None,
    ) -> list[PricePoint]:
        """Fetch historical daily OHLCV series from Yahoo Finance."""
        yf_sym = resolve_yahoo_symbol(symbol, market)
        try:
            ticker_obj = self._get_ticker(yf_sym)
            df = ticker_obj.history(period=range_period, interval="1d")
            if df is None or df.empty:
                return []
            points: list[PricePoint] = []
            for idx, row in df.iterrows():
                close_val = _safe_float(row.get("Close"))
                if close_val is None or close_val <= 0:
                    continue
                pt_date = idx.date() if hasattr(idx, "date") else idx
                points.append(
                    PricePoint(
                        date=pt_date,
                        close=close_val,
                        open=_safe_float(row.get("Open")),
                        high=_safe_float(row.get("High")),
                        low=_safe_float(row.get("Low")),
                        adj_close=close_val,
                        volume=_safe_float(row.get("Volume")),
                    )
                )
            points.sort(key=lambda p: p.date)
            return points
        except Exception:
            return []

    def get_annual_statements(
        self, symbol: str, market: Market | None = None
    ) -> list[FundamentalSnapshot]:
        """Yearly statement history from Yahoo Finance (empty when unavailable)."""
        try:
            return parse_yfinance_statements(
                symbol, self._get_ticker(resolve_yahoo_symbol(symbol, market))
            )
        except Exception:
            return []

    def get_fundamentals(self, symbol: str, market: Market | None = None) -> Fundamentals | None:
        """Fetch fundamental indicators from Yahoo Finance `Ticker.info`."""
        yf_sym = resolve_yahoo_symbol(symbol, market)
        try:
            ticker_obj = self._get_ticker(yf_sym)
            info: dict[str, Any] = getattr(ticker_obj, "info", None) or {}
            if not info:
                return None

            total_debt = _safe_float(info.get("totalDebt"))
            total_cash = _safe_float(info.get("totalCash")) or 0.0
            ebitda = _safe_float(info.get("ebitda"))
            net_debt_ebitda: float | None = None
            if total_debt is not None and ebitda is not None and ebitda > 0:
                net_debt_ebitda = (total_debt - total_cash) / ebitda

            dte_pct = _safe_float(info.get("debtToEquity"))
            dy = _safe_float(info.get("trailingAnnualDividendYield"))
            if dy is None:
                dy_pct = _safe_float(info.get("dividendYield"))
                dy = dy_pct / 100.0 if dy_pct is not None else None
            price = (
                _safe_float(info.get("regularMarketPrice"))
                or _safe_float(info.get("currentPrice"))
                or _safe_float(info.get("previousClose"))
            )

            return Fundamentals(
                symbol=symbol.strip().upper(),
                sector=info.get("sector"),
                industry=info.get("industry"),
                price_to_earnings=_safe_float(info.get("trailingPE"))
                or _safe_float(info.get("forwardPE")),
                price_to_book=_safe_float(info.get("priceToBook")),
                earnings_per_share=_safe_float(info.get("trailingEps")),
                book_value_per_share=_safe_float(info.get("bookValue")),
                dividend_yield=dy,
                dividends_per_share_ttm=_safe_float(info.get("trailingAnnualDividendRate")),
                return_on_equity=_safe_float(info.get("returnOnEquity")),
                profit_margin=_safe_float(info.get("profitMargins")),
                debt_to_equity=dte_pct / 100.0 if dte_pct is not None else None,
                net_debt_to_ebitda=net_debt_ebitda,
                revenue_growth=_safe_float(info.get("revenueGrowth")),
                earnings_growth=_safe_float(info.get("earningsGrowth")),
                market_cap=_safe_float(info.get("marketCap")),
                avg_daily_volume=financial_volume(_safe_float(info.get("averageVolume")), price),
            )
        except Exception:
            return None


_YF_ROWS: dict[str, tuple[str, tuple[str, ...]]] = {
    "revenue": ("income_stmt", ("Total Revenue",)),
    "net_income": ("income_stmt", ("Net Income", "Net Income Common Stockholders")),
    "ebitda": ("income_stmt", ("EBITDA", "Normalized EBITDA")),
    "equity": ("balance_sheet", ("Stockholders Equity", "Common Stock Equity")),
    "total_debt": ("balance_sheet", ("Total Debt",)),
    "cash": ("balance_sheet", ("Cash And Cash Equivalents",)),
    "dividends_paid": ("cashflow", ("Cash Dividends Paid", "Common Stock Dividend Paid")),
}


def parse_yfinance_statements(symbol: str, ticker_obj: Any) -> list[FundamentalSnapshot]:
    """Annual snapshots from yfinance statement DataFrames (rows = items, columns = dates)."""
    by_year: dict[Any, dict[str, float | None]] = {}
    for key, (attribute, labels) in _YF_ROWS.items():
        frame = getattr(ticker_obj, attribute, None)
        if frame is None or getattr(frame, "empty", True):
            continue
        label = next((name for name in labels if name in frame.index), None)
        if label is None:
            continue
        for column, value in frame.loc[label].items():
            ref = column.date() if hasattr(column, "date") else column
            number = _safe_float(value)
            if number is not None:
                by_year.setdefault(ref, {})[key] = number
    return [
        FundamentalSnapshot(
            ticker=symbol.strip().upper(),
            reference_date=ref,
            period=FundamentalPeriod.ANNUAL,
            metrics=metrics,
            source=YFinanceProvider.PROVIDER_NAME,
        )
        for ref, metrics in sorted(by_year.items())
    ]
